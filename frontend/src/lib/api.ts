interface FetchOptions extends RequestInit {
  retries?: number;
  retryDelay?: number;
  timeout?: number;
}

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

// Lazy import to avoid circular deps and keep this module light
let _reportApiError: ((url: string, status: number, message: string) => void) | null = null;
function getReporter() {
  if (!_reportApiError && typeof window !== 'undefined') {
    import('./errorReporter').then(m => { _reportApiError = m.reportApiError; }).catch(() => {});
  }
  return _reportApiError;
}

async function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

export async function apiFetch<T = unknown>(
  url: string,
  options: FetchOptions = {}
): Promise<T> {
  const { retries = 2, retryDelay = 1000, timeout = 30000, ...fetchOptions } = options;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  let lastError: Error | null = null;

  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const response = await fetch(url, {
        ...fetchOptions,
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        if (response.status >= 500 && attempt < retries) {
          lastError = new ApiError(`Server error: ${response.status}`, response.status);
          await sleep(retryDelay * Math.pow(2, attempt));
          continue;
        }
        const apiErr = new ApiError(
          `Request failed: ${response.status} ${response.statusText}`,
          response.status
        );
        getReporter()?.(url, response.status, apiErr.message);
        throw apiErr;
      }

      const contentType = response.headers.get('content-type');
      if (contentType?.includes('application/json')) {
        return await response.json() as T;
      }
      return await response.text() as unknown as T;
    } catch (error) {
      clearTimeout(timeoutId);

      if (error instanceof ApiError) {
        if (attempt >= retries) throw error;
        lastError = error;
        continue;
      }

      if (error instanceof DOMException && error.name === 'AbortError') {
        getReporter()?.(url, 408, 'Request timed out');
        throw new ApiError('Request timed out', 408);
      }

      // Network error — retry
      if (attempt < retries) {
        lastError = error as Error;
        await sleep(retryDelay * Math.pow(2, attempt));
        continue;
      }

      getReporter()?.(url, 0, 'Network error');
      throw new ApiError('Network error — please check your connection', 0);
    }
  }

  throw lastError || new ApiError('Request failed', 0);
}

export { ApiError };
