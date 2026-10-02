
document.addEventListener('DOMContentLoaded', () => {
  // PRODUCT GALLERY
  document.querySelectorAll('.thumb').forEach(thumb => {
    thumb.addEventListener('click', () => {
      const main = document.querySelector('.gallery-main img');
      if (main) main.src = thumb.dataset.image;

      document.querySelectorAll('.thumb').forEach(t =>
        t.classList.remove('active')
      );
      thumb.classList.add('active');
    });
  });

  // CHECKOUT ELEMENTS
  const form = document.getElementById('checkout-form');
  const picker = document.getElementById('variant-picker');
  const hidden = document.getElementById('variant_vid');
  const submit = document.getElementById('checkout-submit');
  const qty = document.getElementById('quantity');
  const total = document.getElementById('checkout-total');
  const line = document.getElementById('line-total');
  const qtyLabel = document.getElementById('qty-label');
  const image = document.getElementById('checkout-image');
  const feedback = document.getElementById('variant-feedback');
  const label = document.getElementById('selected-variant-label');

  if (!form || !qty || !submit) return;

  const basePrice = Number(window.BUYANYTHING_UNIT_PRICE || 0);
  const originalImage = image?.src;
  const selected = {};
  let variants = [];
  let activeVariant = null;
  let submitting = false;

  const clamp = value => {
    const n = Number(value);
    return Number.isFinite(n)
      ? Math.max(1, Math.min(20, Math.trunc(n)))
      : 1;
  };

  // LOAD ONLY SERVER-PROVIDED CJ VARIANTS
  if (picker) {
    try {
      variants = JSON.parse(picker.dataset.variants || '[]');
      if (!Array.isArray(variants)) variants = [];
    } catch (error) {
      console.error('Invalid SP variant data:', error);
    }
  }

  // PRICING AND PRODUCT IMAGE
  function refreshTotals() {
    const q = clamp(qty.value);
    qty.value = q;

    const unit = activeVariant
      ? Number(activeVariant.retail_price ?? basePrice)
      : basePrice;

    const amount = '$' + (unit * q).toFixed(2);

    if (total) total.textContent = amount;
    if (line) line.textContent = amount;
    if (qtyLabel) qtyLabel.textContent = 'Qty ' + q;

    if (image) {
      image.src = activeVariant?.image || originalImage;
    }
  }

  // ENABLE CHECKOUT ONLY FOR A VALID CJ VARIANT
  function setVariant(v) {
    activeVariant = v && v.vid ? v : null;

    if (hidden) hidden.value = activeVariant?.vid || '';

    submit.disabled = submitting || (!!picker && !activeVariant);

    if (feedback) {
      feedback.textContent = activeVariant
        ? 'Selected: ' + activeVariant.name
        : 'Choose an available combination.';

      feedback.classList.toggle('ready', !!activeVariant);
    }

    if (label) {
      label.textContent = activeVariant
        ? activeVariant.name
        : 'Select your options below';
    }

    refreshTotals();
  }

  // RESOLVE ONLY REAL CJ ATTRIBUTE COMBINATIONS
  if (picker) {
    const groups = [
      ...picker.querySelectorAll('.option-group[data-option-label]')
    ];

    const matches = (v, choices) =>
      Object.entries(choices).every(([key, value]) =>
        v.attributes &&
        String(v.attributes[key]) === String(value)
      );

    function resolve() {
      const labels = groups.map(g => g.dataset.optionLabel);

      const complete =
        labels.length > 0 &&
        labels.every(key =>
          Object.prototype.hasOwnProperty.call(selected, key)
        );

      const candidates = variants.filter(v => matches(v, selected));

      // Multiple CJ IDs can share display attributes; select a real
      // matching ID rather than leaving a valid combination unselectable.
      const exact = complete && candidates.length
        ? candidates[0]
        : null;

      setVariant(exact);

      if (!exact && complete && feedback) { 
        feedback.textContent =
          'That combination is unavailable. Choose another option.';
      }

      // DISABLE ONLY COMBINATIONS ABSENT FROM CJ DATA
      picker.querySelectorAll(
        '.option-chip:not(.direct-variant)'
      ).forEach(btn => {
        // Ignore the old choice in this same group when switching values.
        const test = { ...selected };
        test[btn.dataset.option] = btn.dataset.value;

        const possible = variants.some(v => matches(v, test));

        btn.classList.toggle('unavailable', !possible);
        btn.disabled = !possible;
      });
    }

    // FRIENDLY COLOR / SIZE / STYLE SELECTORS
    picker.querySelectorAll(
      '.option-chip:not(.direct-variant)'
    ).forEach(btn => {
      btn.addEventListener('click', () => {
        selected[btn.dataset.option] = btn.dataset.value;
        // If the new value conflicts with a previously chosen other group,
        // clear conflicting choices so the shopper can choose a valid pair.
        for (const key of Object.keys(selected)) {
          if (key !== btn.dataset.option &&
              !variants.some(v => matches(v, selected))) {
            delete selected[key];
            picker.querySelectorAll('.option-chip:not(.direct-variant)').forEach(other => {
              if (other.dataset.option === key) other.classList.remove('selected');
            });
          }
        }

        picker.querySelectorAll(
          '.option-chip:not(.direct-variant)'
        ).forEach(other => {
          if (other.dataset.option === btn.dataset.option) {
            other.classList.toggle('selected', other === btn);
          }
        });

        resolve();
      });
    });

    // DIRECT CJ VARIANT FALLBACK
    picker.querySelectorAll('.direct-variant').forEach(btn => {
      btn.addEventListener('click', () => {
        const v = variants.find(item =>
          String(item.vid) === String(btn.dataset.vid)
        );

        picker.querySelectorAll('.direct-variant').forEach(other =>
          other.classList.toggle('selected', other === btn)
        );

        setVariant(v || null);
      });
    });

    // INITIALIZE
    if (groups.length) {
      resolve();
    } else {
      setVariant(null);
    }
  } else {
    submit.disabled = false;
  }

  // QUANTITY CONTROLS
  document.querySelectorAll('.qty-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      qty.value = clamp(
        Number(qty.value) + Number(btn.dataset.step)
      );
      refreshTotals();
    });
  });

  qty.addEventListener('input', refreshTotals);
  qty.addEventListener('change', refreshTotals);

  // SECURE CHECKOUT SUBMISSION
  form.addEventListener('submit', event => {
    if (submitting || (picker && !activeVariant)) {
      event.preventDefault();
      return;
    }

    qty.value = clamp(qty.value);

    if (!form.checkValidity()) return;

    submitting = true;
    submit.disabled = true;
    submit.textContent = 'Redirecting to secure payment…';
  });

  refreshTotals();
});
