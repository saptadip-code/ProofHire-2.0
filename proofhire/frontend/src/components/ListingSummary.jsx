import {
  APPLICATION_CHANNEL_OPTIONS,
  EMPLOYMENT_TYPE_OPTIONS,
  INTERVIEW_MODE_OPTIONS,
  WORK_MODE_OPTIONS,
  labelFor,
} from '../lib/constants.js';
import { formatInr, salaryRange } from '../lib/format.js';
import { missingListingDetails } from '../lib/insights.js';

// Echo of the submitted listing (ListingInput), so the report shows what was assessed, plus a plain
// list of the optional details that were left out. Everything shown here is user-provided and unverified.
export default function ListingSummary({ listing }) {
  if (!listing) return null;
  const missing = missingListingDetails(listing);
  const rows = [
    ['Company', listing.company_name],
    ['Location', listing.location || 'Not provided'],
    ['Work mode', labelFor(WORK_MODE_OPTIONS, listing.work_mode)],
    ['Employment type', labelFor(EMPLOYMENT_TYPE_OPTIONS, listing.employment_type)],
    ['Pay', salaryRange(listing)],
    ['Upfront fee requested', listing.upfront_fee_amount > 0 ? formatInr(listing.upfront_fee_amount) : 'None entered'],
    ['How to apply', labelFor(APPLICATION_CHANNEL_OPTIONS, listing.application_channel)],
    ['Interview', labelFor(INTERVIEW_MODE_OPTIONS, listing.interview_mode)],
    ['Contact email', listing.contact_email || 'Not provided'],
    ['Contact phone', listing.contact_phone || 'Not provided'],
    ['Company website', listing.company_website || 'Not provided'],
  ];
  return (
    <div className="card">
      <h2 className="card__title">Submitted listing</h2>
      <p className="muted small">User-provided details. ProofHire has not verified that they are true.</p>
      <dl className="detail-list">
        {rows.map(([term, value]) => (
          <div key={term} className="detail-list__row">
            <dt>{term}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>

      <h3 className="card__subtitle">Details not provided</h3>
      {missing.length === 0 ? (
        <p className="muted">All the optional details were included in this listing.</p>
      ) : (
        <>
          <ul className="missing-list">
            {missing.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <p className="muted small">
            Missing details were not checked. Ask the employer for them before you decide.
          </p>
        </>
      )}
    </div>
  );
}
