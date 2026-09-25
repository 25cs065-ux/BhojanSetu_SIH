/* ============================================================
   BhojanSetu — login.js
   Handles login, signup, and OTP form interactions.
   All form submissions target live Flask auth routes:
     POST /auth/login, POST /auth/signup, POST /auth/verify-otp
   ============================================================ */

'use strict';

/* ── Shared helpers ──────────────────────────────────────── */

function _showError(elId, msg) {
  const el = document.getElementById(elId);
  if (el) { el.textContent = msg; el.style.display = ''; }
}

function _hideError(elId) {
  const el = document.getElementById(elId);
  if (el) el.style.display = 'none';
}

function _setLoading(btnId, textId, spinnerId, loading) {
  const btn = document.getElementById(btnId);
  const txt = document.getElementById(textId);
  const spin = document.getElementById(spinnerId);
  if (btn) btn.disabled = loading;
  if (txt) txt.style.display = loading ? 'none' : '';
  if (spin) spin.style.display = loading ? '' : 'none';
}

/* ── Login form ──────────────────────────────────────────── */

const loginForm = document.getElementById('loginForm');
if (loginForm) {
  loginForm.addEventListener('submit', async function (e) {
    e.preventDefault();
    _hideError('loginError');
    _hideError('emailErr');
    _hideError('passwordErr');

    const email = document.getElementById('email').value.trim();
    const password = document.getElementById('password').value;

    // Client-side validation
    let valid = true;
    if (!email) {
      _showError('emailErr', 'Email is required.');
      valid = false;
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      _showError('emailErr', 'Enter a valid email address.');
      valid = false;
    }
    if (!password) {
      _showError('passwordErr', 'Password is required.');
      valid = false;
    }
    if (!valid) return;

    _setLoading('loginBtn', 'loginBtnText', 'loginSpinner', true);

    try {
      loginForm.submit();
    } catch (err) {
      _setLoading('loginBtn', 'loginBtnText', 'loginSpinner', false);
      _showError('loginErrorMsg', 'Unable to connect. Please try again.');
      document.getElementById('loginError').style.display = '';
    }
  });
}

/* ── Signup form ─────────────────────────────────────────── */

const signupForm = document.getElementById('signupForm');
if (signupForm) {
  signupForm.addEventListener('submit', function (e) {
    _hideError('signupError');
    _hideError('nameErr');
    _hideError('roleErr');
    _hideError('regEmailErr');
    _hideError('regPwdErr');
    _hideError('confirmPwdErr');

    const name     = document.getElementById('full_name')?.value.trim();
    const role     = document.getElementById('role')?.value;
    const email    = document.getElementById('reg_email')?.value.trim();
    const pwd      = document.getElementById('reg_password')?.value;
    const confirm  = document.getElementById('confirm_password')?.value;

    let valid = true;

    if (!name)    { _showError('nameErr', 'Full name is required.'); valid = false; }
    if (!role)    { _showError('roleErr', 'Please select a role.'); valid = false; }
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      _showError('regEmailErr', 'Enter a valid email address.'); valid = false;
    }
    if (!pwd || pwd.length < 8) {
      _showError('regPwdErr', 'Password must be at least 8 characters.'); valid = false;
    }
    if (pwd !== confirm) {
      _showError('confirmPwdErr', 'Passwords do not match.'); valid = false;
    }

    if (!valid) { e.preventDefault(); return; }

    _setLoading('signupBtn', 'signupBtnText', 'signupSpinner', true);
    // Form submits natively to POST /auth/signup
  });
}

/* ── OTP form ────────────────────────────────────────────── */

const otpForm = document.getElementById('otpForm');
if (otpForm) {
  otpForm.addEventListener('submit', function (e) {
    _hideError('otpErr');
    const otp = document.getElementById('otp')?.value.trim();
    if (!otp || !/^\d{6}$/.test(otp)) {
      e.preventDefault();
      _showError('otpErr', 'Enter a valid 6-digit OTP.');
      return;
    }
    _setLoading('otpBtn', 'otpBtnText', 'otpSpinner', true);
    // Form submits natively to POST /auth/verify-otp
  });
}
