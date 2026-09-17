document.querySelectorAll('[data-quiz]').forEach((form) => {
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const selected = form.querySelector('input:checked');
    const feedback = form.querySelector('[data-feedback]');
    if (!selected) {
      feedback.textContent = '请先选择一个答案，再检查。';
      return;
    }
    feedback.textContent = selected.value === form.dataset.answer
      ? `正确。${form.dataset.explanation}`
      : `再想一次：${form.dataset.hint}`;
  });
});
