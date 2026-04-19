import { useState, useRef } from 'react';
import { startScan, pollScan } from '../utils/api';

const POLL_INTERVAL_MS = 2500;
const MAX_POLLS = 120; // 5 minutes

/**
 * Hook that drives the full async scan lifecycle.
 * Returns { scan, status, error, loading, submit }
 */
export function useScan() {
  const [status, setStatus] = useState('idle'); // idle | pending | running | done | error
  const [scan, setScan] = useState(null);
  const [error, setError] = useState(null);
  const pollRef = useRef(null);
  const pollCount = useRef(0);

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  async function submit(githubUrl, useCase = '', forceRefresh = false) {
    stopPolling();
    setScan(null);
    setError(null);
    pollCount.current = 0;

    try {
      setStatus('pending');
      const job = await startScan(githubUrl, useCase, forceRefresh);

      pollRef.current = setInterval(async () => {
        pollCount.current += 1;
        if (pollCount.current > MAX_POLLS) {
          stopPolling();
          setStatus('error');
          setError('Scan timed out. Try again.');
          return;
        }

        try {
          const jobStatus = await pollScan(job.job_id);
          setStatus(jobStatus.status);

          if (jobStatus.status === 'done') {
            stopPolling();
            setScan(jobStatus.result);
          } else if (jobStatus.status === 'error') {
            stopPolling();
            setError(jobStatus.error || 'Unknown error');
          }
        } catch (pollErr) {
          stopPolling();
          setStatus('error');
          setError(pollErr.message);
        }
      }, POLL_INTERVAL_MS);
    } catch (submitErr) {
      setStatus('error');
      setError(submitErr.response?.data?.detail || submitErr.message);
    }
  }

  return { scan, status, error, loading: status === 'pending' || status === 'running', submit };
}
