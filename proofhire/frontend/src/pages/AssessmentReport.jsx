import { useCallback, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Flag, GitCompare, Link2, Printer } from 'lucide-react';
import RiskGauge from '../components/RiskGauge.jsx';
import RiskBadge from '../components/RiskBadge.jsx';
import ExplanationCard from '../components/ExplanationCard.jsx';
import EvidencePanel from '../components/EvidencePanel.jsx';
import ChecklistPanel from '../components/ChecklistPanel.jsx';
import ConnectionsCard from '../components/ConnectionsCard.jsx';
import ListingSummary from '../components/ListingSummary.jsx';
import ReportModal from '../components/ReportModal.jsx';
import ScoreContext from '../components/ScoreContext.jsx';
import ReportNav from '../components/ReportNav.jsx';
import ReportStats from '../components/ReportStats.jsx';
import Reveal from '../components/Reveal.jsx';
import ErrorBanner from '../components/ErrorBanner.jsx';
import Skeleton from '../components/Skeleton.jsx';
import AnnotatedListing from '../components/AnnotatedListing.jsx';
import MiniScoreBar from '../components/MiniScoreBar.jsx';
import ScoreDrivers from '../components/ScoreDrivers.jsx';
import { getAssessment, setChecklistItemDone } from '../api/assessments.js';
import { useAuth } from '../context/AuthContext.jsx';
import { useToast } from '../context/ToastContext.jsx';
import { useAsync } from '../hooks/useAsync.js';
import { DISCLAIMER } from '../lib/constants.js';
import { prefersReducedMotion } from '../hooks/usePrefersReducedMotion.js';
import { formatDate, pluralize } from '../lib/format.js';

const SECTIONS = [
  { id: 'sec-score', label: 'Score' },
  { id: 'sec-explanation', label: 'Explanation' },
  { id: 'sec-annotated', label: 'Marked listing' },
  { id: 'sec-drivers', label: 'Score drivers' },
  { id: 'sec-evidence', label: 'Evidence' },
  { id: 'sec-checklist', label: 'Checklist' },
  { id: 'sec-patterns', label: 'Repeat patterns' },
  { id: 'sec-listing', label: 'Listing' },
];

function ReportSkeleton() {
  return (
    <div className="report-grid" aria-busy="true">
      <div className="card">
        <Skeleton lines={4} height={20} label="Loading risk score" />
      </div>
      <div className="card">
        <Skeleton lines={5} label="Loading explanation" />
      </div>
      <div className="card report-grid__full">
        <Skeleton lines={6} label="Loading evidence" />
      </div>
    </div>
  );
}

export default function AssessmentReport() {
  const { id } = useParams();
  const { user } = useAuth();

  const { data, error, loading, run } = useAsync((signal) => getAssessment(id, { signal }), { deps: [id] });
  const [highlight, setHighlight] = useState(null);
  const [reportOpen, setReportOpen] = useState(false);
  const [activeMark, setActiveMark] = useState(null);
  const toast = useToast();

  // Key-concern chips highlight (and the panel scrolls to) the matching evidence item.
  const selectEvidence = (evidenceId) => {
    setActiveMark(evidenceId);
    setHighlight({ id: evidenceId, nonce: Date.now() });
  };

  // From an evidence card back to its phrase in the marked listing.
  const showInListing = useCallback((evidenceId) => {
    setActiveMark(evidenceId);
    const el = document.getElementById(`annot-mark-${evidenceId}`);
    if (!el) return;
    el.scrollIntoView({ behavior: prefersReducedMotion() ? 'auto' : 'smooth', block: 'center' });
    el.focus({ preventScroll: true });
  }, []);

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      toast.push('Link copied.');
    } catch {
      toast.push('Could not copy the link. Copy it from the address bar.', { tone: 'info' });
    }
  }

  const toggleChecklist = (item, done) => setChecklistItemDone(data.assessment_id, item.id, done);

  if (loading) {
    return (
      <div className="container page">
        <ReportSkeleton />
      </div>
    );
  }
  if (error || !data) {
    return (
      <div className="container page page--narrow">
        <ErrorBanner error={error || 'This assessment could not be loaded.'} title="Could not load the report" onRetry={run} />
        <Link to="/assess" className="btn btn-secondary">
          Assess a new listing
        </Link>
      </div>
    );
  }

  const approved = Number(data.report_count_approved) || 0;

  return (
    <div className="container page">
      <header className="report-header">
        <div>
          <h1 className="page__title">{data.listing?.title}</h1>
          <p className="muted">
            {data.listing?.company_name} · Assessed {formatDate(data.created_at)}
          </p>
        </div>
        <div className="report-header__side">
          <RiskBadge level={data.risk_level} />
          <div className="report-header__tools" data-print-hide>
            <button type="button" className="btn btn-secondary btn-sm" onClick={copyLink}>
              <Link2 size={14} aria-hidden="true" />
              Copy link
            </button>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => window.print()}>
              <Printer size={14} aria-hidden="true" />
              Print or save as PDF
            </button>
          </div>
        </div>
      </header>

      <MiniScoreBar targetId="sec-score" title={data.listing?.title} score={data.risk_score} level={data.risk_level} />

      <ReportStats data={data} />
      <ReportNav sections={SECTIONS} />

      <div className="report-grid">
        <Reveal as="section" id="sec-score" tabIndex={-1} className="report-section" aria-label="Risk estimate">
          <div className="card report-score">
            <h2 className="card__title">Risk estimate</h2>
            <RiskGauge score={data.risk_score} level={data.risk_level} thresholds={data.thresholds} />
            <ScoreContext level={data.risk_level} score={data.risk_score} thresholds={data.thresholds} />
            <p className="muted small center">Model version: {data.model_version}</p>
            <p className="muted small center">
              {approved} approved community {pluralize(approved, 'report')}
            </p>
          </div>
        </Reveal>
        <Reveal as="section" id="sec-explanation" tabIndex={-1} delay={100} className="report-section" aria-label="Explanation">
          <ExplanationCard explanation={data.explanation} onSelectEvidence={selectEvidence} />
        </Reveal>
        <Reveal as="section" id="sec-annotated" tabIndex={-1} className="report-section report-grid__full" aria-label="Listing with evidence marked">
          <AnnotatedListing
            text={data.listing?.description}
            evidence={data.evidence}
            activeId={activeMark}
            onSelect={selectEvidence}
          />
        </Reveal>
        <Reveal as="section" id="sec-drivers" tabIndex={-1} className="report-section report-grid__full" aria-label="What moved the estimate">
          <ScoreDrivers evidence={data.evidence} />
        </Reveal>
        <Reveal as="section" id="sec-evidence" tabIndex={-1} className="report-section report-grid__full" aria-label="Evidence">
          <EvidencePanel
            evidence={data.evidence}
            highlightId={highlight?.id}
            highlightNonce={highlight?.nonce}
            onShowInListing={showInListing}
          />
        </Reveal>
        <Reveal as="section" id="sec-checklist" tabIndex={-1} className="report-section" aria-label="Verification checklist">
          <ChecklistPanel items={data.checklist} onToggle={toggleChecklist} />
        </Reveal>
        <Reveal as="section" id="sec-patterns" tabIndex={-1} delay={100} className="report-section" aria-label="Repeat patterns">
          <ConnectionsCard connections={data.connections} />
        </Reveal>
        <Reveal as="section" id="sec-listing" tabIndex={-1} className="report-section report-grid__full" aria-label="Submitted listing">
          <ListingSummary listing={data.listing} />
        </Reveal>
      </div>

      <div className="report-actions" data-print-hide>
        <button type="button" className="btn btn-secondary" onClick={() => setReportOpen(true)}>
          <Flag size={16} aria-hidden="true" />
          Report this listing
        </button>
        <Link to={`/compare?a=${encodeURIComponent(id)}`} className="btn btn-secondary">
          <GitCompare size={16} aria-hidden="true" />
          Compare with another
        </Link>
        <Link to="/assess" className="btn btn-primary">
          Assess another listing
        </Link>
      </div>
      {!user && (
        <p className="muted small" data-print-hide>
          <Link to="/login">Sign in</Link> to keep a saved list of your assessments.
        </p>
      )}

      <p className="disclaimer-inline">{data.disclaimer || DISCLAIMER}</p>

      <ReportModal
        assessmentId={data.assessment_id}
        open={reportOpen}
        onClose={() => setReportOpen(false)}
        onSuccess={(message) => toast.push(message)}
      />
    </div>
  );
}
