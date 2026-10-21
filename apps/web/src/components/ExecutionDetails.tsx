import type { Execution } from '../types/order'
import Status from './Status'

export function ExecutionDetails({ execution }: { execution: Execution }) {
  return <article className="execution-card">
    <h4>Execution <code>{execution.id}</code></h4>
    <p><Status value={execution.status} /> · {String(execution.definition_snapshot.name)} · version {String(execution.definition_snapshot.version)}</p>
    <p>Started: {execution.started_at ? new Date(execution.started_at).toLocaleString() : 'Pending'}<br />
      Finished: {execution.completed_at ? new Date(execution.completed_at).toLocaleString() : 'Not finished'}</p>
    {execution.error_message && <p role="alert">{execution.error_category}: {execution.error_message}</p>}
    <ol className="step-list">{execution.steps.map(step => <li key={step.id}>
      <strong>{step.step_name.replaceAll('_', ' ')}</strong> <Status value={step.status} />
      <span>Attempt {step.attempt_number}</span>
      {step.external_reference && <p>Provider reference: <code>{step.external_reference}</code></p>}
      {step.error_message && <p className="error-message">{step.error_category}: {step.error_message}</p>}
      {step.status === 'unknown' && <p>Outcome is uncertain. Check the provider before retrying.</p>}
      <details><summary>Request and result</summary><pre>{JSON.stringify({ input: step.input_summary, output: step.output_summary }, null, 2)}</pre></details>
    </li>)}</ol>
    {execution.status === 'completed' && <p>Fulfillment request accepted. Delivery is outside this workflow.</p>}
  </article>
}


