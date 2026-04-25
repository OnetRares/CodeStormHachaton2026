const API_BASE_URL = 'http://localhost:8000';

export async function batchUpdate(oldText, newText, options = {}) {
  const formData = new FormData();
  formData.append('old_text', oldText);
  formData.append('new_text', newText);
  formData.append('json_dir', options.jsonDir || 'pdf');

  if (options.targetJsonFile) {
    formData.append('target_json_file', options.targetJsonFile);
  }

  const response = await fetch(`${API_BASE_URL}/batch-update`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const errorData = await response.json();
    throw new Error(errorData.detail?.message || 'Failed to perform batch update');
  }

  return response.json();
}
