import { NavLink } from 'react-router-dom';
import { config } from '../../config';

interface Tab {
  path: string;
  label: string;
  icon?: string;
}

const tabs: Tab[] = [
  { path: '/', label: 'Welcome' },
  { path: '/account', label: 'My Personas' },
  { path: '/my-trips', label: config.terminology.myWorkflows },
  { path: '/invite', label: 'Invite' },
  { path: '/delegate', label: 'Delegate' },
];

export function TabNavigation() {
  return (
    <nav className="bg-white border-b border-gray-200 shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex space-x-8">
          {tabs.map((tab) => (
            <NavLink
              key={tab.path}
              to={tab.path}
              className={({ isActive }) =>
                `py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                  isActive
                    ? 'border-nura-orange text-nura-orange'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`
              }
            >
              {tab.label}
            </NavLink>
          ))}
        </div>
      </div>
    </nav>
  );
}
