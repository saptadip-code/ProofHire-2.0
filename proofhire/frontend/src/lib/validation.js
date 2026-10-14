// Client-side validation that mirrors Section 5.2 (ListingInput). The server stays the authority.

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const PHONE_RE = /^[0-9\s+\-()]*$/;
const INT_RE = /^\d+$/;
const CURRENCY_RE = /^[A-Za-z]{3}$/;
const URL_RE = /^https?:\/\//i;

export const FIELD_LIMITS = {
  title: { min: 3, max: 200 },
  company_name: { min: 2, max: 200 },
  description: { min: 20, max: 8000 },
  requirements: { max: 4000 },
  location: { max: 200 },
  contact_email: { max: 255 },
  contact_phone: { max: 32 },
  company_website: { max: 500 },
};

// Human labels for error summaries (keys match the ListingInput field names).
export const FIELD_LABELS = {
  title: 'Job title',
  company_name: 'Company name',
  description: 'Listing description',
  requirements: 'Requirements',
  location: 'Location',
  salary_min: 'Minimum pay',
  salary_max: 'Maximum pay',
  currency: 'Currency',
  contact_email: 'Contact email',
  contact_phone: 'Contact phone',
  company_website: 'Company website',
  upfront_fee_amount: 'Upfront fee',
};

export const INITIAL_VALUES = {
  title: '',
  company_name: '',
  description: '',
  requirements: '',
  location: '',
  work_mode: 'onsite',
  employment_type: 'internship',
  salary_min: '',
  salary_max: '',
  pay_period: 'month',
  currency: 'INR',
  contact_email: '',
  contact_phone: '',
  application_channel: 'unknown',
  company_website: '',
  upfront_fee_amount: '0',
  interview_mode: 'none',
};

export function validateListing(values) {
  const errors = {};
  const title = values.title.trim();
  const company = values.company_name.trim();
  const description = values.description.trim();

  if (title.length < FIELD_LIMITS.title.min || title.length > FIELD_LIMITS.title.max) {
    errors.title = `Title must be ${FIELD_LIMITS.title.min} to ${FIELD_LIMITS.title.max} characters.`;
  }
  if (company.length < FIELD_LIMITS.company_name.min || company.length > FIELD_LIMITS.company_name.max) {
    errors.company_name = `Company name must be ${FIELD_LIMITS.company_name.min} to ${FIELD_LIMITS.company_name.max} characters.`;
  }
  if (description.length < FIELD_LIMITS.description.min || description.length > FIELD_LIMITS.description.max) {
    errors.description = `Description must be ${FIELD_LIMITS.description.min} to ${FIELD_LIMITS.description.max} characters.`;
  }
  if (values.requirements.trim().length > FIELD_LIMITS.requirements.max) {
    errors.requirements = `Requirements can be at most ${FIELD_LIMITS.requirements.max} characters.`;
  }
  if (values.location.trim().length > FIELD_LIMITS.location.max) {
    errors.location = `Location can be at most ${FIELD_LIMITS.location.max} characters.`;
  }

  const min = values.salary_min.trim();
  const max = values.salary_max.trim();
  if (min && !INT_RE.test(min)) errors.salary_min = 'Enter a whole number of 0 or more.';
  if (max && !INT_RE.test(max)) errors.salary_max = 'Enter a whole number of 0 or more.';
  if (!errors.salary_min && !errors.salary_max && min && max && Number(max) < Number(min)) {
    errors.salary_max = 'Maximum must be greater than or equal to the minimum.';
  }

  if (!CURRENCY_RE.test(values.currency.trim())) {
    errors.currency = 'Use a 3-letter currency code, for example INR.';
  }

  const email = values.contact_email.trim();
  if (email) {
    if (!EMAIL_RE.test(email) || email.length > FIELD_LIMITS.contact_email.max) {
      errors.contact_email = 'Enter a valid email address.';
    }
  }

  const phone = values.contact_phone.trim();
  if (phone) {
    if (!PHONE_RE.test(phone) || phone.length > FIELD_LIMITS.contact_phone.max) {
      errors.contact_phone = 'Use digits, spaces, +, -, ( and ) only, up to 32 characters.';
    }
  }

  const website = values.company_website.trim();
  if (website) {
    if (!URL_RE.test(website)) errors.company_website = 'The website must start with http:// or https://.';
    else if (website.length > FIELD_LIMITS.company_website.max) {
      errors.company_website = `The website can be at most ${FIELD_LIMITS.company_website.max} characters.`;
    }
  }

  const fee = values.upfront_fee_amount.trim();
  if (fee && !INT_RE.test(fee)) {
    errors.upfront_fee_amount = 'Enter a whole number of 0 or more (use 0 if no fee was asked).';
  }

  return errors;
}

const orNull = (v) => {
  const t = v.trim();
  return t === '' ? null : t;
};

// Builds the exact ListingInput body: integers as numbers, blank optional fields as null.
export function toPayload(values) {
  const toInt = (v) => (v.trim() === '' ? null : Number.parseInt(v.trim(), 10));
  return {
    title: values.title.trim(),
    company_name: values.company_name.trim(),
    description: values.description.trim(),
    requirements: orNull(values.requirements),
    location: orNull(values.location),
    work_mode: values.work_mode,
    employment_type: values.employment_type,
    salary_min: toInt(values.salary_min),
    salary_max: toInt(values.salary_max),
    pay_period: values.pay_period,
    currency: values.currency.trim().toUpperCase(),
    contact_email: orNull(values.contact_email),
    contact_phone: orNull(values.contact_phone),
    application_channel: values.application_channel,
    company_website: orNull(values.company_website),
    upfront_fee_amount: toInt(values.upfront_fee_amount) ?? 0,
    interview_mode: values.interview_mode,
  };
}
