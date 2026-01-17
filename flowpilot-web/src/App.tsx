import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './state/AuthContext';
import { AppStateProvider } from './state/AppStateContext';
import { AppLayout } from './components/layout/AppLayout';
import { WelcomePanel } from './components/panels/WelcomePanel';
import { MyAccountPanel } from './components/panels/MyAccountPanel';
import { MyTripPanel } from './components/panels/MyTripPanel';
import { BookPanel } from './components/panels/BookPanel';
import { InvitePanel } from './components/panels/InvitePanel';
import { DelegatePanel } from './components/panels/DelegatePanel';

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-gray-500">Loading...</div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/account" replace />;
  }

  return <>{children}</>;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<AppLayout />}>
        <Route index element={<WelcomePanel />} />
        <Route path="account" element={<MyAccountPanel />} />
        <Route
          path="trips"
          element={
            <ProtectedRoute>
              <MyTripPanel />
            </ProtectedRoute>
          }
        />
        <Route
          path="book"
          element={
            <ProtectedRoute>
              <BookPanel />
            </ProtectedRoute>
          }
        />
        <Route
          path="invite"
          element={
            <ProtectedRoute>
              <InvitePanel />
            </ProtectedRoute>
          }
        />
        <Route
          path="delegate"
          element={
            <ProtectedRoute>
              <DelegatePanel />
            </ProtectedRoute>
          }
        />
      </Route>
    </Routes>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppStateProvider>
          <AppRoutes />
        </AppStateProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
