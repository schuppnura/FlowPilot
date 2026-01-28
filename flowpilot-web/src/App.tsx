import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider, useAuth } from './state/AuthContext';
import { AppStateProvider } from './state/AppStateContext';
import { AppLayout } from './components/layout/AppLayout';
import { WelcomePanel } from './components/panels/WelcomePanel';
import { MyAccountPanel } from './components/panels/MyAccountPanel';
import { MyTripsPanel } from './components/panels/MyTripsPanel';
import { MySharingPanel } from './components/panels/MySharingPanel';
import { SignInModal } from './components/common/SignInModal';

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading, openSignInModal } = useAuth();

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-gray-500">Loading...</div>
      </div>
    );
  }

  // If not authenticated, show the content but trigger sign-in modal
  if (!user) {
    // Trigger modal to open
    setTimeout(() => openSignInModal(), 0);
  }

  return <>{children}</>;
}

function AppRoutes() {
  const { showSignInModal, closeSignInModal } = useAuth();

  return (
    <>
      <Routes>
        <Route path="/" element={<AppLayout />}>
          <Route index element={<WelcomePanel />} />
          <Route path="account" element={<MyAccountPanel />} />
          <Route
            path="my-trips"
            element={
              <ProtectedRoute>
                <MyTripsPanel />
              </ProtectedRoute>
            }
          />
          <Route
            path="my-sharing"
            element={
              <ProtectedRoute>
                <MySharingPanel />
              </ProtectedRoute>
            }
          />
        </Route>
      </Routes>
      
      {/* Global Sign In Modal */}
      <SignInModal isOpen={showSignInModal} onClose={closeSignInModal} />
    </>
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
