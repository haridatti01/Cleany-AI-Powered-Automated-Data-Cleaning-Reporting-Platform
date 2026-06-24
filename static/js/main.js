// static/js/main.js
// Global front-end behaviors for Cleany

document.addEventListener('DOMContentLoaded', () => {
  // Auto-dismiss alerts after 5 seconds
  document.querySelectorAll('.alert').forEach((alert) => {
    setTimeout(() => {
      const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
      bsAlert.close();
    }, 5000);
  });

  // Show a spinner / disable button on file upload form submit
  const uploadForm = document.querySelector('form[action*="upload"]');
  if (uploadForm) {
    uploadForm.addEventListener('submit', () => {
      const btn = uploadForm.querySelector('button[type="submit"]');
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Uploading...';
      }
    });
  }
});
