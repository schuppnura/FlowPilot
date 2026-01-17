import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../state/AuthContext';

export function WelcomePanel() {
  const navigate = useNavigate();
  const { user } = useAuth();

  const handleCreateTrip = () => {
    if (!user) {
      navigate('/account');
    } else {
      navigate('/trips');
    }
  };

  const handleManageTrip = () => {
    if (!user) {
      navigate('/account');
    } else {
      navigate('/trips');
    }
  };

  return (
    <div className="relative min-h-[600px] rounded-lg overflow-hidden shadow-lg">
      {/* Background Image */}
      <div
        className="absolute inset-0 bg-cover bg-center"
        style={{
          backgroundImage: 'url(/images/nura-home.jpg)',
        }}
      >
        {/* Overlay */}
        <div className="absolute inset-0 bg-black bg-opacity-40"></div>
      </div>

      {/* Content */}
      <div className="relative z-10 flex flex-col items-center justify-center min-h-[600px] px-4 py-16">
        <div className="text-center mb-12">
          <h1 className="text-5xl font-light text-white mb-4">FlowPilot</h1>
          <p className="text-xl text-white text-opacity-90">
            Policy-driven authorization & delegation for AI-powered workflows
          </p>
        </div>

        <div className="flex flex-col sm:flex-row gap-4">
          <button
            onClick={handleCreateTrip}
            className="px-8 py-4 bg-nura-orange text-white font-medium rounded-lg shadow-md hover:bg-opacity-90 transition-all transform hover:scale-105"
          >
            Create New Trip
          </button>
          <button
            onClick={handleManageTrip}
            className="px-8 py-4 bg-white bg-opacity-20 backdrop-blur-sm text-white font-medium rounded-lg border-2 border-white hover:bg-opacity-30 transition-all transform hover:scale-105"
          >
            Manage My Trip
          </button>
        </div>
      </div>
    </div>
  );
}
