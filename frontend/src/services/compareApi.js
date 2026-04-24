const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

function normalizeErrorPayload(payload) {
  if (!payload) return 'Failed to compare PDF files.';
  if (typeof payload === 'string') return payload;

  if (payload.detail) {
    if (typeof payload.detail === 'string') return payload.detail;
    if (payload.detail.message) return payload.detail.message;
    return JSON.stringify(payload.detail);
  }

  if (payload.message) return payload.message;
  return 'Failed to compare PDF files.';
}

function toAbsoluteUrl(urlPath) {
  if (!urlPath) return null;
  if (urlPath.startsWith('http://') || urlPath.startsWith('https://')) {
    return urlPath;
  }
  return `${API_BASE_URL}${urlPath}`;
}

export async function comparePdfsVisual(leftPdf, rightPdf) {
  const formData = new FormData();
  formData.append('left_pdf', leftPdf);
  formData.append('right_pdf', rightPdf);

  const response = await fetch(`${API_BASE_URL}/compare/visual-pdf`, {
    method: 'POST',
    body: formData,
  });

  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(normalizeErrorPayload(payload));
  }

  return {
    ...payload,
    html_report_url: toAbsoluteUrl(payload?.html_report_url),
  };
}
