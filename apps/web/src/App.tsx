
import './App.css'

function App() {
  return (
    <div className="app">
      <header className="header">
        <h1>BridgOps</h1>
        <span>Retail Integration & Workflow Platform</span>
      </header>

      <main className="main">
        <h2>Operations Dashboard</h2>
        <p>
          Manage business integrations, automate workflows,
          and monitor operations from one platform.
        </p>

        <section className="features">
          <article className="feature-card">
            <h3>Tenants</h3>
            <p>Manage registered retail businesses.</p>
            <span>API available</span>
          </article>

          <article className="feature-card">
            <h3>Orders</h3>
            <p>Track orders across connected systems.</p>
            <span>Coming later</span>
          </article>

          <article className="feature-card">
            <h3>Integrations</h3>
            <p>Connect external business applications.</p>
            <span>Coming later</span>
          </article>

          <article className="feature-card">
            <h3>Workflows</h3>
            <p>Automate and monitor operational processes.</p>
            <span>Coming later</span>
          </article>
        </section>
      </main>
    </div>
  )
}

export default App
