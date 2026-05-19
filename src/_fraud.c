#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <numpy/arrayobject.h>
#include <math.h>
#include <string.h>
#include <stdlib.h>

#define N_DIMS 14
#define K 5
#define NPROBE 2
#define MAX_CANDIDATES 200
#define MAX_TOTAL_CANDIDATES (NPROBE * MAX_CANDIDATES)

static float clampf(float x) {
    if (x < 0.0f) return 0.0f;
    if (x > 1.0f) return 1.0f;
    return x;
}

typedef struct {
    float max_amount;
    float max_installments;
    float amount_vs_avg_ratio;
    float max_minutes;
    float max_km;
    float max_tx_count_24h;
    float max_merchant_avg_amount;
} NormParams;

static NormParams g_norm;

static PyArrayObject *g_centroids_arr = NULL;
static PyArrayObject *g_vectors_q_arr = NULL;
static PyArrayObject *g_labels_arr = NULL;
static PyArrayObject *g_dim_min_arr = NULL;
static PyArrayObject *g_dim_scale_arr = NULL;

static int *g_lists_ptrs[256];
static int g_lists_counts[256];
static int g_n_centroids = 0;

static PyObject *g_mcc_risk_dict = NULL;

static int parse_iso_datetime_hour_weekday(const char *s, int *hour, int *weekday) {
    int y, mo, d, h, mi, sec;
    if (sscanf(s, "%d-%d-%dT%d:%d:%d", &y, &mo, &d, &h, &mi, &sec) < 6) {
        return -1;
    }
    *hour = h;

    int a = (14 - mo) / 12;
    int yy = y + 4800 - a;
    int mm = mo + 12 * a - 3;
    int jdn = d + (153 * mm + 2) / 5 + 365 * yy + yy / 4 - yy / 100 + yy / 400 - 32045;
    *weekday = (jdn + 1) % 7;
    if (*weekday == 0) *weekday = 6;
    else *weekday -= 1;

    return 0;
}

static int parse_iso_datetime_to_minutes(const char *s, long long *total_minutes) {
    int y, mo, d, h, mi, sec;
    if (sscanf(s, "%d-%d-%dT%d:%d:%d", &y, &mo, &d, &h, &mi, &sec) < 6) {
        return -1;
    }
    *total_minutes = (long long)h * 60 + mi;
    return 0;
}

static int search_c(float *query_q) {
    float *centroids = (float *)PyArray_DATA(g_centroids_arr);
    int n_centroids = g_n_centroids;

    float min_dists[NPROBE];
    int min_ids[NPROBE];
    for (int i = 0; i < NPROBE; i++) {
        min_dists[i] = 1e30f;
        min_ids[i] = -1;
    }

    for (int c = 0; c < n_centroids; c++) {
        float *cen = centroids + c * N_DIMS;
        float dist = 0.0f;
        for (int d = 0; d < N_DIMS; d++) {
            float diff = cen[d] - query_q[d];
            dist += diff * diff;
        }
        for (int j = 0; j < NPROBE; j++) {
            if (dist < min_dists[j]) {
                for (int jj = NPROBE - 1; jj > j; jj--) {
                    min_dists[jj] = min_dists[jj - 1];
                    min_ids[jj] = min_ids[jj - 1];
                }
                min_dists[j] = dist;
                min_ids[j] = c;
                break;
            }
        }
    }

    int8_t *all_vectors = (int8_t *)PyArray_DATA(g_vectors_q_arr);
    int32_t *labels = (int32_t *)PyArray_DATA(g_labels_arr);
    int n_vectors = (int)PyArray_DIM(g_vectors_q_arr, 0);

    int8_t query_i8[N_DIMS];
    for (int d = 0; d < N_DIMS; d++) {
        float v = query_q[d];
        if (v < -128.0f) v = -128.0f;
        if (v > 127.0f) v = 127.0f;
        query_i8[d] = (int8_t)roundf(v);
    }

    int cand_indices[MAX_TOTAL_CANDIDATES];
    float cand_dists[MAX_TOTAL_CANDIDATES];
    int n_candidates = 0;

    for (int p = 0; p < NPROBE; p++) {
        int cid = min_ids[p];
        if (cid < 0) continue;
        int count = g_lists_counts[cid];
        int *indices = g_lists_ptrs[cid];
        int limit = count < MAX_CANDIDATES ? count : MAX_CANDIDATES;
        for (int i = 0; i < limit; i++) {
            if (n_candidates >= MAX_TOTAL_CANDIDATES) goto done;
            int idx = indices[i];
            if (idx < 0 || idx >= n_vectors) continue;
            cand_indices[n_candidates] = idx;
            int8_t *vec = all_vectors + idx * N_DIMS;
            float dist = 0.0f;
            for (int d = 0; d < N_DIMS; d++) {
                float diff = (float)vec[d] - (float)query_i8[d];
                dist += diff * diff;
            }
            cand_dists[n_candidates] = dist;
            n_candidates++;
        }
    }
done:

    if (n_candidates < K) return 0;

    int top_k[K];
    for (int i = 0; i < K; i++) {
        top_k[i] = i;
    }
    for (int i = K; i < n_candidates; i++) {
        float max_dist = -1.0f;
        int max_j = 0;
        for (int j = 0; j < K; j++) {
            if (cand_dists[top_k[j]] > max_dist) {
                max_dist = cand_dists[top_k[j]];
                max_j = j;
            }
        }
        if (cand_dists[i] < max_dist) {
            top_k[max_j] = i;
        }
    }

    int fraud_count = 0;
    for (int i = 0; i < K; i++) {
        if (labels[cand_indices[top_k[i]]] == 1) fraud_count++;
    }

    return fraud_count;
}

static PyObject *py_detect(PyObject *self, PyObject *args) {
    PyObject *payload;

    if (!PyArg_ParseTuple(args, "O", &payload))
        return NULL;

    float vec[N_DIMS];

    PyObject *tx = PyDict_GetItemString(payload, "transaction");
    PyObject *customer = PyDict_GetItemString(payload, "customer");
    PyObject *merchant = PyDict_GetItemString(payload, "merchant");
    PyObject *terminal = PyDict_GetItemString(payload, "terminal");
    PyObject *last_tx = PyDict_GetItemString(payload, "last_transaction");

    double amount = PyFloat_AsDouble(PyDict_GetItemString(tx, "amount"));
    vec[0] = clampf((float)(amount / g_norm.max_amount));

    long long installments = PyLong_AsLongLong(PyDict_GetItemString(tx, "installments"));
    vec[1] = clampf((float)installments / g_norm.max_installments);

    double avg_amount = PyFloat_AsDouble(PyDict_GetItemString(customer, "avg_amount"));
    vec[2] = clampf((float)((amount / avg_amount) / g_norm.amount_vs_avg_ratio));

    PyObject *requested_at = PyDict_GetItemString(tx, "requested_at");
    const char *dt_str = PyUnicode_AsUTF8(requested_at);
    int hour, weekday;
    parse_iso_datetime_hour_weekday(dt_str, &hour, &weekday);
    vec[3] = (float)hour / 23.0f;
    vec[4] = (float)weekday / 6.0f;

    if (last_tx == Py_None) {
        vec[5] = -1.0f;
        vec[6] = -1.0f;
    } else {
        PyObject *last_ts = PyDict_GetItemString(last_tx, "timestamp");
        const char *last_dt_str = PyUnicode_AsUTF8(last_ts);
        long long cur_minutes, last_minutes;
        long long y, mo, d, h, mi, sec;
        sscanf(dt_str, "%lld-%lld-%lldT%lld:%lld:%lld", &y, &mo, &d, &h, &mi, &sec);
        cur_minutes = y * 525600LL + mo * 43200LL + d * 1440LL + h * 60LL + mi;
        sscanf(last_dt_str, "%lld-%lld-%lldT%lld:%lld:%lld", &y, &mo, &d, &h, &mi, &sec);
        last_minutes = y * 525600LL + mo * 43200LL + d * 1440LL + h * 60LL + mi;
        double minutes_diff = (double)(cur_minutes - last_minutes);
        vec[5] = clampf((float)(minutes_diff / g_norm.max_minutes));

        double km = PyFloat_AsDouble(PyDict_GetItemString(last_tx, "km_from_current"));
        vec[6] = clampf((float)(km / g_norm.max_km));
    }

    double km_home = PyFloat_AsDouble(PyDict_GetItemString(terminal, "km_from_home"));
    vec[7] = clampf((float)(km_home / g_norm.max_km));

    long long tx_count = PyLong_AsLongLong(PyDict_GetItemString(customer, "tx_count_24h"));
    vec[8] = clampf((float)tx_count / g_norm.max_tx_count_24h);

    int is_online = PyObject_IsTrue(PyDict_GetItemString(terminal, "is_online"));
    vec[9] = is_online ? 1.0f : 0.0f;

    int card_present = PyObject_IsTrue(PyDict_GetItemString(terminal, "card_present"));
    vec[10] = card_present ? 1.0f : 0.0f;

    PyObject *known_merchants = PyDict_GetItemString(customer, "known_merchants");
    PyObject *merchant_id = PyDict_GetItemString(merchant, "id");
    int is_unknown = 1;
    Py_ssize_t n_merchants = PyList_Size(known_merchants);
    for (Py_ssize_t i = 0; i < n_merchants; i++) {
        if (PyObject_RichCompareBool(PyList_GetItem(known_merchants, i), merchant_id, Py_EQ)) {
            is_unknown = 0;
            break;
        }
    }
    vec[11] = is_unknown ? 1.0f : 0.0f;

    PyObject *mcc_obj = PyDict_GetItemString(merchant, "mcc");
    const char *mcc_str = PyUnicode_AsUTF8(mcc_obj);
    PyObject *risk_obj = PyDict_GetItemString(g_mcc_risk_dict, mcc_str);
    vec[12] = risk_obj ? (float)PyFloat_AsDouble(risk_obj) : 0.5f;

    double merchant_avg = PyFloat_AsDouble(PyDict_GetItemString(merchant, "avg_amount"));
    vec[13] = clampf((float)(merchant_avg / g_norm.max_merchant_avg_amount));

    float *dim_min = (float *)PyArray_DATA(g_dim_min_arr);
    float *dim_scale = (float *)PyArray_DATA(g_dim_scale_arr);

    float query_q[N_DIMS];
    for (int i = 0; i < N_DIMS; i++) {
        float v = (vec[i] - dim_min[i]) * dim_scale[i] - 127.0f;
        if (v < -128.0f) v = -128.0f;
        if (v > 127.0f) v = 127.0f;
        query_q[i] = v;
    }

    int fraud_count;
    Py_BEGIN_ALLOW_THREADS
    fraud_count = search_c(query_q);
    Py_END_ALLOW_THREADS

    float fraud_score = (float)fraud_count / 5.0f;
    int approved = fraud_score < 0.6f;

    PyObject *result = PyDict_New();
    PyDict_SetItemString(result, "approved", PyBool_FromLong(approved));
    PyDict_SetItemString(result, "fraud_score", PyFloat_FromDouble(fraud_score));
    return result;
}

static PyObject *py_init_index(PyObject *self, PyObject *args) {
    PyObject *data_dict;

    if (!PyArg_ParseTuple(args, "O", &data_dict))
        return NULL;

    Py_XDECREF(g_centroids_arr);
    Py_XDECREF(g_vectors_q_arr);
    Py_XDECREF(g_labels_arr);
    Py_XDECREF(g_dim_min_arr);
    Py_XDECREF(g_dim_scale_arr);

    g_centroids_arr = (PyArrayObject *)PyDict_GetItemString(data_dict, "centroids");
    g_vectors_q_arr = (PyArrayObject *)PyDict_GetItemString(data_dict, "vectors_q");
    g_labels_arr = (PyArrayObject *)PyDict_GetItemString(data_dict, "labels");
    g_dim_min_arr = (PyArrayObject *)PyDict_GetItemString(data_dict, "dim_min");
    g_dim_scale_arr = (PyArrayObject *)PyDict_GetItemString(data_dict, "dim_scale");

    Py_INCREF(g_centroids_arr);
    Py_INCREF(g_vectors_q_arr);
    Py_INCREF(g_labels_arr);
    Py_INCREF(g_dim_min_arr);
    Py_INCREF(g_dim_scale_arr);

    g_n_centroids = (int)PyArray_DIM(g_centroids_arr, 0);

    PyObject *lists_obj = PyDict_GetItemString(data_dict, "lists");
    g_n_centroids = (int)PyList_Size(lists_obj);
    for (int i = 0; i < g_n_centroids && i < 256; i++) {
        PyArrayObject *arr = (PyArrayObject *)PyList_GetItem(lists_obj, i);
        g_lists_ptrs[i] = (int *)PyArray_DATA(arr);
        g_lists_counts[i] = (int)PyArray_SIZE(arr);
    }

    Py_RETURN_NONE;
}

static PyObject *py_init_norm(PyObject *self, PyObject *args) {
    PyObject *norm_dict;

    if (!PyArg_ParseTuple(args, "O", &norm_dict))
        return NULL;

    g_norm.max_amount = (float)PyFloat_AsDouble(PyDict_GetItemString(norm_dict, "max_amount"));
    g_norm.max_installments = (float)PyFloat_AsDouble(PyDict_GetItemString(norm_dict, "max_installments"));
    g_norm.amount_vs_avg_ratio = (float)PyFloat_AsDouble(PyDict_GetItemString(norm_dict, "amount_vs_avg_ratio"));
    g_norm.max_minutes = (float)PyFloat_AsDouble(PyDict_GetItemString(norm_dict, "max_minutes"));
    g_norm.max_km = (float)PyFloat_AsDouble(PyDict_GetItemString(norm_dict, "max_km"));
    g_norm.max_tx_count_24h = (float)PyFloat_AsDouble(PyDict_GetItemString(norm_dict, "max_tx_count_24h"));
    g_norm.max_merchant_avg_amount = (float)PyFloat_AsDouble(PyDict_GetItemString(norm_dict, "max_merchant_avg_amount"));

    Py_RETURN_NONE;
}

static PyObject *py_init_mcc(PyObject *self, PyObject *args) {
    PyObject *mcc_dict;

    if (!PyArg_ParseTuple(args, "O", &mcc_dict))
        return NULL;

    Py_XDECREF(g_mcc_risk_dict);
    g_mcc_risk_dict = mcc_dict;
    Py_INCREF(g_mcc_risk_dict);

    Py_RETURN_NONE;
}

static PyMethodDef FraudMethods[] = {
    {"detect", py_detect, METH_VARARGS, "Detect fraud for a transaction"},
    {"init_index", py_init_index, METH_VARARGS, "Initialize index data"},
    {"init_norm", py_init_norm, METH_VARARGS, "Initialize normalization params"},
    {"init_mcc", py_init_mcc, METH_VARARGS, "Initialize MCC risk dict"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef fraudmodule = {
    PyModuleDef_HEAD_INIT,
    "_fraud",
    "C extension for fraud detection",
    -1,
    FraudMethods
};

PyMODINIT_FUNC PyInit__fraud(void) {
    import_array();
    return PyModule_Create(&fraudmodule);
}
