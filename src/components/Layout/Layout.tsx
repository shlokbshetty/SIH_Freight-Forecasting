import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import Header from './Header';
import DataStatusProvider from '../../context/DataStatusProvider';
import './Layout.css';

export default function Layout() {
  return (
    <DataStatusProvider>
      <div className="app-shell">
        <Sidebar />
        <div className="app-shell__main">
          <Header />
          <main className="app-shell__content">
            <Outlet />
          </main>
        </div>
      </div>
    </DataStatusProvider>
  );
}
