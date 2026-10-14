// Plain-language helpers for the report. Every sentence is derived from fields the API really returns
// (direction, severity, weight, snippet, thresholds, listing values). Nothing here invents evidence,
// sources or confidence values.

export const EVIDENCE_ORIGIN = {
  observed: { label: 'Observed in the listing', detail: 'Found in the text and details you submitted.' },
  model: { label: 'Model-derived', detail: 'A pattern the model learned from its synthetic training data.' },
};

const NEAR_BOUNDARY = 0.05;

const LEVEL_GUIDANCE = {
  low: 'Few risk patterns were found in the details you submitted. This is not a guarantee of safety, so still complete the checklist.',
  medium: 'Some risk patterns were found. Treat this as a prompt to check the employer, not as a conclusion about them.',
  high: 'Several risk patterns were found. This does not prove the employer is fraudulent. Verify the employer before sharing documents or paying anything.',
};

export function levelGuidance(level) {
  return LEVEL_GUIDANCE[level] || 'The risk level could not be read for this assessment.';
}

const num = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : null);

/**
 * When the score sits within 5 points of a threshold, say so. Returns null otherwise or if the
 * score/thresholds are unusable.
 */
export function boundaryNote(score, thresholds) {
  const s = num(score);
  const low = num(thresholds?.low);
  const high = num(thresholds?.high);
  if (s === null || low === null || high === null) return null;
  if (Math.abs(s - low) <= NEAR_BOUNDARY) {
    return 'This score is close to the boundary between low and medium risk, so a small change in the details could change the level.';
  }
  if (Math.abs(s - high) <= NEAR_BOUNDARY) {
    return 'This score is close to the boundary between medium and high risk, so a small change in the details could change the level.';
  }
  return null;
}

/**
 * Why a signal counts, in order: where it came from, which way it pushes, how strong, and (for
 * model patterns) what the weight means. Returns an array of { term, text } rows.
 */
export function explainEvidence(item) {
  if (!item || typeof item !== 'object') return [];
  const increases = item.direction === 'increases_risk';
  const origin = EVIDENCE_ORIGIN[item.type] || null;
  const rows = [];

  if (origin) rows.push({ term: 'Where it comes from', text: `${origin.label}. ${origin.detail}` });
  rows.push({
    term: 'Effect on the estimate',
    text: increases ? 'It raises the estimated risk.' : 'It lowers the estimated risk.',
  });

  const severity = num(item.severity);
  if (severity !== null) rows.push({ term: 'Severity', text: `${Math.min(3, Math.max(0, severity))} out of 3.` });

  if (item.type === 'model') {
    const weight = num(item.weight);
    if (weight !== null) {
      rows.push({
        term: 'Model weight',
        text: `${weight.toFixed(2)}. ${weight >= 0 ? 'A positive weight means this wording was linked to risky listings' : 'A negative weight means this wording was linked to lower-risk listings'} in the model's synthetic training data.`,
      });
    }
  } else if (item.snippet) {
    rows.push({ term: 'Matched text', text: `"${item.snippet}"` });
  } else {
    rows.push({ term: 'Matched text', text: 'No specific text is attached to this signal, for example because a detail is missing.' });
  }

  if (item.code) rows.push({ term: 'Signal code', text: String(item.code) });
  return rows;
}

const blank = (v) => v === null || v === undefined || (typeof v === 'string' && v.trim() === '');

/**
 * Optional details the listing did not include. A fee of 0 is a real answer, so it is not listed.
 * Only reports what is actually absent from the submitted listing.
 */
export function missingListingDetails(listing) {
  if (!listing || typeof listing !== 'object') return [];
  const missing = [];
  if (blank(listing.contact_email)) missing.push('Contact email');
  if (blank(listing.contact_phone)) missing.push('Contact phone');
  if (blank(listing.company_website)) missing.push('Company website');
  if (blank(listing.location)) missing.push('Location');
  if (blank(listing.requirements)) missing.push('Requirements');
  if (blank(listing.salary_min) && blank(listing.salary_max)) missing.push('Pay');
  if (listing.application_channel === 'unknown') missing.push('How to apply');
  if (listing.interview_mode === 'none') missing.push('Interview process');
  return missing;
}
