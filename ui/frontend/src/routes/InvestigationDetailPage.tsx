import { useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  SummaryHeader,
  InvestigationStep,
  RelatedKbPanel,
  StepEvidence,
  FailureNotice,
  NotFoundMessage,
  DetailSkeleton,
  useIsNarrowViewport,
  type RelatedKbPanelState,
} from '../lib'
import { useInvestigationDetail } from './useInvestigationDetail'
import {
  apiStepTypeToStepType,
  findFirstEvidenceStepOrder,
  statusToBadgeVariant,
} from './investigation-detail-mappers'
import type { InvestigationDetailMetadata, InvestigationStepDto } from '../api/investigation-detail'

/** Stable empty-array reference so `useMemo`'s dep doesn't change identity every render while loading/erroring. */
const EMPTY_STEPS: InvestigationStepDto[] = []

/**
 * InvestigationDetailPage — the investigation-detail "incident hero" (Task 2.5).
 *
 * Renders the INITIAL state from the Task 1.6 one-shot detail fetch
 * (`GET /api/v1/investigations/{id}`, via `useInvestigationDetail` /
 * `src/api/investigation-detail.ts`, which Task 2.5 owns). LIVE streaming
 * (SSE) is Task 2.6 — nothing here subscribes to the events stream.
 *
 * The `SummaryHeader`'s `<h1>` carries `headingId="detail-summary-heading"`
 * — the contract `useRouteFocusManagement` (Task 2.1) targets on every
 * detail-route mount, including a cold permalink load. The header renders
 * unconditionally on every render path below (loading/ok/error — everything
 * except the distinct not-found state) using whatever is known
 * synchronously (the `investigationId` URL param as a service-name
 * fallback) merged with fetched metadata once it resolves, so the heading
 * never waits on the network request to paint (NFR19: first-seconds facts
 * visible without interaction; also required so focus management doesn't
 * race the fetch on a cold load).
 */
export function InvestigationDetailPage() {
  const { investigationId } = useParams<{ investigationId: string }>()
  const query = useInvestigationDetail(investigationId)
  const isNarrowViewport = useIsNarrowViewport()
  const [kbExpanded, setKbExpanded] = useState(false)

  const steps: InvestigationStepDto[] = query.status === 'ok' ? query.data.steps : EMPTY_STEPS
  const firstEvidenceOrder = useMemo(() => findFirstEvidenceStepOrder(steps), [steps])

  if (query.status === 'not-found') {
    return <NotFoundMessage investigationId={investigationId ?? ''} />
  }

  const metadata: InvestigationDetailMetadata | null = query.status === 'ok' ? query.data.metadata : null
  const serviceName = metadata?.service ?? investigationId ?? ''
  const severity = metadata?.severity ?? '—'
  const signalCount = metadata?.signal_count ?? 0
  const statusVariant = metadata != null ? statusToBadgeVariant(metadata.status) : 'pending'
  const problemState = metadata?.condition ?? undefined
  const timestamp = formatTimestamp(metadata)

  const kbStep = steps.find((step) => step.type === 'kb')
  const kbPanelState: RelatedKbPanelState =
    kbStep != null && kbStep.state !== 'completed' && kbStep.state !== 'error' ? 'loading' : 'populated'
  // "Populated" here still covers the zero-entries case — RelatedKbPanel
  // itself renders "0 Related KB Entries" (not an error) whenever
  // entryCount is 0, exactly matching FR26's "absent/unparseable KB"
  // requirement. `kbEntries` is a forward-compatible field (see
  // src/api/investigation-detail.ts doc) — absent from the Task 1.6
  // payload today, so entryCount is 0 until the backend adds it.
  const kbEntries = kbStep?.kbEntries ?? []

  const isFailed = metadata?.status === 'failed'
  const isPending = metadata?.status === 'pending'

  return (
    <div data-testid="investigation-detail-page" className="flex flex-col gap-6 pb-16">
      <SummaryHeader
        headingId="detail-summary-heading"
        serviceName={serviceName}
        severity={severity}
        signalCount={signalCount}
        statusVariant={statusVariant}
        timestamp={timestamp}
        problemState={problemState}
      />

      {query.status === 'loading' ? (
        <DetailSkeleton />
      ) : query.status === 'error' ? (
        <p role="alert" className="text-base text-status-critical">
          Unable to load this investigation right now.
        </p>
      ) : isPending ? (
        <p data-testid="pending-placeholder" className="text-base text-text-secondary">
          Investigation is waiting to start.
        </p>
      ) : (
        <ol data-slot="investigation-steps" className="flex flex-col gap-2">
          {steps.map((step) => (
            <InvestigationStep
              key={step.order}
              type={apiStepTypeToStepType(step.type)}
              order={step.order}
              description={step.label ?? ''}
              isFirstEvidence={firstEvidenceOrder === step.order}
              evidence={
                step.evidence != null && step.evidence.length > 0 ? (
                  <StepEvidence evidence={step.evidence} />
                ) : undefined
              }
            />
          ))}
        </ol>
      )}

      {query.status === 'ok' && isFailed ? <FailureNotice message={metadata?.message} /> : null}

      {query.status === 'ok' ? (
        <p data-field="correlation-placeholder" className="text-sm text-text-secondary">
          {metadata?.correlated_services != null && metadata.correlated_services.length > 0
            ? `Impact: ${metadata.correlated_services.join(', ')}`
            : 'Impact: not yet correlated'}
        </p>
      ) : null}

      {query.status === 'ok' ? (
        <RelatedKbPanel
          state={kbPanelState}
          entryCount={kbEntries.length}
          expanded={kbExpanded}
          onExpandedChange={setKbExpanded}
          className={
            isNarrowViewport
              ? undefined // Inline, normal document flow (<1200px) — spec's "stacks below investigation content"
              : 'fixed inset-x-0 bottom-0 z-10' // Anchored bottom bar, expands upward (>=1200px)
          }
        >
          {kbEntries.length > 0 ? (
            <ul className="flex flex-col gap-2 text-sm text-text-primary">
              {kbEntries.map((entry) => (
                <li key={entry.id}>{entry.title}</li>
              ))}
            </ul>
          ) : null}
        </RelatedKbPanel>
      ) : null}
    </div>
  )
}

function formatTimestamp(metadata: InvestigationDetailMetadata | null): string | undefined {
  if (metadata == null) return undefined
  if (metadata.status === 'completed' && metadata.completed_at != null) {
    return `Completed ${metadata.completed_at}`
  }
  if (metadata.started_at != null) {
    return `Started ${metadata.started_at}`
  }
  return undefined
}
