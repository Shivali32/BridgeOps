
import TenantList from './components/TenantList'
import OrderDashboard from './components/OrderDashboard'
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

        <TenantList />
        <OrderDashboard />
      </main>
    </div>
  )
}

export default App
