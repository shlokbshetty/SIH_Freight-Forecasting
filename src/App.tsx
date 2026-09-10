import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout/Layout';
import CommandCenter from './pages/CommandCenter';
import MapPage from './pages/Map';
import Evaluate from './pages/Evaluate';
import Forecast from './pages/Forecast';
import Matcher from './pages/Matcher';
import ContractComparison from './pages/ContractComparison';
import MarketTiming from './pages/MarketTiming';
import IdlePlanner from './pages/IdlePlanner';
import RiskAlerts from './pages/RiskAlerts';
import VoyageEditor from './pages/VoyageEditor';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index                 element={<CommandCenter />}      />
          <Route path="/map"           element={<MapPage />}            />
          <Route path="/evaluate"      element={<Evaluate />}           />
          <Route path="/forecast"      element={<Forecast />}           />
          <Route path="/matcher"       element={<Matcher />}            />
          <Route path="/contracts"     element={<ContractComparison />} />
          <Route path="/timing"        element={<MarketTiming />}       />
          <Route path="/idle"          element={<IdlePlanner />}        />
          <Route path="/risk"          element={<RiskAlerts />}         />
          <Route path="/voyage-editor" element={<VoyageEditor />}       />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
