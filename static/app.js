document.addEventListener('DOMContentLoaded', () => {
  const assignmentMode = document.getElementById('assignment-mode');
  const manualSlotField = document.getElementById('manual-slot-field');
  const slotSelect = document.getElementById('slot-id');
  const updateAssignmentMode = () => {
    if (!assignmentMode || !manualSlotField) return;
    const manual = assignmentMode.value === 'manual';
    manualSlotField.hidden = !manual;
    if (slotSelect) slotSelect.required = manual;
  };
  if (assignmentMode) { assignmentMode.addEventListener('change', updateAssignmentMode); updateAssignmentMode(); }
  document.querySelectorAll('input[type="datetime-local"]').forEach(input => {
    input.addEventListener('change', () => {
      const form = input.closest('form');
      if (!form) return;
      const start = form.querySelector('[name="start_at"]');
      const end = form.querySelector('[name="end_at"]');
      if (start && end && start.value && end.value && end.value <= start.value) {
        end.setCustomValidity('Departure must be after arrival.');
      } else if (end) end.setCustomValidity('');
    });
  });
});
