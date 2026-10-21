/** Gateway/tunnel hiccups (502-504) and dropped connections are transient; reads are safe to repeat. */
const TRANSIENT = [502, 503, 504];
const RETRY_DELAYS = [400, 1200];
const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** Repeats GET/HEAD requests that failed with a gateway error or a dropped connection; anything else is returned as is. */
export async function fetchWithRetry(url: string, init: RequestInit): Promise<Response> {
  const idempotent = !init.method || ['GET', 'HEAD'].includes(init.method.toUpperCase());
  for (let attempt = 0; ; attempt++) {
    const retryable = idempotent && attempt < RETRY_DELAYS.length;
    try {
      const response = await fetch(url, init);
      if (!retryable || !TRANSIENT.includes(response.status)) return response;
    } catch (error) {
      if (!retryable || (error as Error).name === 'AbortError') throw error;
    }
    await wait(RETRY_DELAYS[attempt]);
  }
}

