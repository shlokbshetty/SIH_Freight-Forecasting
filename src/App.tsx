import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout/Layout';
import CommandCenter from './pages/CommandCenter';
import MapPage from './pages/Map';
import Forecast from './pages/Forecast';
import Matcher from './pages/Matcher';
import ContractComparison from './pages/ContractComparison';
import RiskAlerts from './pages/RiskAlerts';
import Evaluate from './pages/Evaluate';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index              element={<CommandCenter />}      />
          <Route path="/map"        element={<MapPage />}            />
          <Route path="/forecast"   element={<Forecast />}           />
          <Route path="/matcher"    element={<Matcher />}            />
          <Route path="/contracts"  element={<ContractComparison />} />
          <Route path="/evaluate"   element={<Evaluate />}           />
          <Route path="/risk"       element={<RiskAlerts />}         />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
