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

function normalizeValidationErrorPayload(payload) {
  if (!payload) return 'Validation failed.';
  if (typeof payload === 'string') return payload;

  const detail = payload.detail;
  if (typeof detail === 'string') return detail;
  if (detail?.message) return detail.message;

  if (Array.isArray(detail?.errors) && detail.errors.length > 0) {
    return detail.errors.join('; ');
  }

  if (payload.message) return payload.message;
  return 'Validation failed.';
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

export async function validateFdAgainstPlanMaster(fisaPdf, planPdf, options = {}) {
  const formData = new FormData();
  formData.append('fisa_pdf', fisaPdf);
  formData.append('plan_pdf', planPdf);

  if (typeof options.is_fisa_scanned === 'boolean') {
    formData.append('is_fisa_scanned', String(options.is_fisa_scanned));
  }
  if (typeof options.is_plan_scanned === 'boolean') {
    formData.append('is_plan_scanned', String(options.is_plan_scanned));
  }
  if (typeof options.ocr_lang === 'string' && options.ocr_lang.trim() !== '') {
    formData.append('ocr_lang', options.ocr_lang.trim());
  }

  const response = await fetch(`${API_BASE_URL}/validate`, {
    method: 'POST',
    body: formData,
  });

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(normalizeValidationErrorPayload(payload));
  }

  return payload;
}

export async function fetchCompetencySubjects() {
  const response = await fetch(`${API_BASE_URL}/competencies/subjects`);
  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(normalizeValidationErrorPayload(payload));
  }

  return Array.isArray(payload?.subjects) ? payload.subjects : [];
}

export async function fetchRecommendedCompetencies(subject) {
  const query = new URLSearchParams({ subject: String(subject || '').trim() });
  const response = await fetch(`${API_BASE_URL}/competencies/recommend?${query.toString()}`);
  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(normalizeValidationErrorPayload(payload));
  }

  return {
    subject: payload?.subject || String(subject || '').trim(),
    competencies: Array.isArray(payload?.competencies) ? payload.competencies : [],
    count: Number(payload?.count || 0),
  };
}

export async function fetchWeightsHoursCheck(dbPath = 'data/discipline_new.db') {
  const query = new URLSearchParams({ db_path: String(dbPath || '').trim() || 'data/discipline_new.db' });
  const response = await fetch(`${API_BASE_URL}/checks/weights-hours?${query.toString()}`);
  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(normalizeValidationErrorPayload(payload));
  }

  return payload;
}
