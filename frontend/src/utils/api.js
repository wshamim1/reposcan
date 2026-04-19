import axios from 'axios';

const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: BASE,
  timeout: 30000,
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    // Axios uses this shape for transport-level failures (DNS, refused, CORS, backend down).
    if (!error.response && error.code === 'ERR_NETWORK') {
      return Promise.reject(new Error(`Cannot reach backend at ${BASE}. Ensure backend is running.`));
    }
    return Promise.reject(error);
  }
);

/** Start an async scan. Returns { job_id, status } */
export async function startScan(githubUrl, useCase = '', forceRefresh = false) {
  const payload = {
    github_url: githubUrl,
    use_case: useCase?.trim() || null,
    force_refresh: !!forceRefresh,
  };
  const { data } = await api.post('/api/scan', payload);
  return data;
}

/** Poll a scan job until done or error. */
export async function pollScan(jobId) {
  const { data } = await api.get(`/api/scan/${jobId}`);
  return data;
}

/** Fetch graphs without LLM (fast path). */
export async function fetchGraphs(githubUrl) {
  const { data } = await api.get('/api/graphs', {
    params: { github_url: githubUrl },
  });
  return data;
}

/** Fetch similar repos only. */
export async function fetchSimilar(githubUrl) {
  const { data } = await api.get('/api/similar', {
    params: { github_url: githubUrl },
  });
  return data;
}

/** Fetch scan history from cache. */
export async function fetchHistory() {
  const { data } = await api.get('/api/history');
  return data;
}

/** Delete one history item by GitHub URL. */
export async function deleteHistoryEntry(githubUrl) {
  const { data } = await api.delete('/api/history', {
    params: { github_url: githubUrl },
  });
  return data;
}

/** Clear all history entries. */
export async function clearHistory() {
  const { data } = await api.delete('/api/history');
  return data;
}

/** Search GitHub repos by keywords. */
export async function searchRepos(keywords, limit = 8) {
  const { data } = await api.get('/api/search-repos', {
    params: { keywords, limit },
  });
  return data;
}

/** Execute a setup script from UI (backend executes in controlled shell). */
export async function executeSetupScript(script, timeoutSeconds = 90, workingDir = null) {
  const { data } = await api.post('/api/execute-script', {
    script,
    timeout_seconds: timeoutSeconds,
    working_dir: workingDir,
  });
  return data;
}
