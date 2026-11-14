let csrf = '';
let pendingToken;

export function resetCsrf() {
  csrf = '';
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch('/api' + path, { credentials: 'include', ...options });
  } catch {
    throw new Error('Нет связи с сервером. Проверьте, что Flask запущен, и повторите действие.');
  }
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error('Сервер вернул неожиданный ответ. Проверьте терминал Flask и адрес API.');
  }
  return { response, data };
}

async function token() {
  if (!pendingToken) {
    pendingToken = request('/csrf').then(({ response, data }) => {
      if (!response.ok || !data.token) throw new Error('Не удалось получить защитный токен.');
      csrf = data.token;
    }).finally(() => { pendingToken = null; });
  }
  await pendingToken;
}

export async function api(path, method = 'GET', body) {
  const write = !['GET', 'HEAD'].includes(method);
  if (write && !csrf) await token();
  const send = () => request(path, {
    method,
    headers: {
      ...(body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...(write ? { 'X-CSRFToken': csrf } : {}),
    },
    body: body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body),
  });
  let result = await send();
  // CSRF rejection happens before the route executes: only this error is safe to retry.
  if (write && result.response.status === 400 && result.data.code === 'csrf_failed') {
    csrf = '';
    await token();
    result = await send();
  }
  if (!result.response.ok) {
    const error = new Error(result.data.error || 'Не удалось выполнить действие.');
    error.status = result.response.status;
    throw error;
  }
  return result.data;
}
