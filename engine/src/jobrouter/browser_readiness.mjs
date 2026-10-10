// A bounded stability gate, independent of global networkidle heuristics.
export function readinessGate(stableMilliseconds = 500) {
  let signature = null;
  let since = null;
  return (snapshot, activeRequests, candidate, now) => {
    const next = JSON.stringify(snapshot);
    if (!candidate || activeRequests !== 0) {
      signature = null;
      since = null;
      return false;
    }
    if (next !== signature) { signature = next; since = now; }
    return now - since >= stableMilliseconds;
  };
}

export function trackRequests(context, stage, problems) {
  const active = new Set();
  context.on('request', request => active.add(request));
  context.on('requestfinished', request => active.delete(request));
  context.on('requestfailed', request => {
    active.delete(request);
    problems.push({reason_code: 'browser_request_failed', url: request.url().slice(0, 8192),
      method: request.method(), resource_type: request.resourceType(), stage: stage(),
      error: String(request.failure()?.errorText || 'Browser resource failed').slice(0, 500)});
  });
  return active;
}
