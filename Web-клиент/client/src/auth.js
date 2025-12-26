// helper for opening popup login
export function openAuthPopup(provider = 'google') {
  const popup = window.open(`/auth/start/${provider}`, 'auth_popup', 'width=500,height=700')
  // The payload will be posted into window.opener by the server HTML wrapper
  // No further action required here.
  return popup
}
