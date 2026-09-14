import { useState } from "react";
import { useAuth } from "./auth/AuthContext";
import { LoginScreen } from "./screens/LoginScreen";
import { MissionListScreen } from "./screens/MissionListScreen";
import { MissionDetailScreen } from "./screens/MissionDetailScreen";
import { MyAssignmentsScreen } from "./screens/MyAssignmentsScreen";
import { AssignmentsNavIcon, MissionsNavIcon, Sidebar } from "./components/Sidebar";
import { Spinner } from "./components/Spinner";

/** Mission Lead / Director: mission list -> mission detail. No router —
 * two screens deep, local `useState` is the whole navigation stack
 * (PRD §7: "no routing depth" for this showcase). */
function MissionsSection() {
  const [selectedMissionId, setSelectedMissionId] = useState<number | null>(null);

  return (
    <div className="flex min-h-screen">
      <Sidebar navLabel="Missions" navIcon={MissionsNavIcon} />
      {selectedMissionId === null ? (
        <MissionListScreen onSelectMission={setSelectedMissionId} />
      ) : (
        <MissionDetailScreen missionId={selectedMissionId} onBack={() => setSelectedMissionId(null)} />
      )}
    </div>
  );
}

function CrewSection() {
  return (
    <div className="flex min-h-screen">
      <Sidebar navLabel="My assignments" navIcon={AssignmentsNavIcon} />
      <MyAssignmentsScreen />
    </div>
  );
}

export default function App() {
  const { status, user } = useAuth();

  if (status === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg">
        <Spinner className="h-6 w-6 text-text-3" />
      </div>
    );
  }

  if (status === "unauthenticated" || !user) {
    return <LoginScreen />;
  }

  // Role-conditional rendering off the logged-in user's role (§10 #23):
  // Director/Mission Lead run missions; Crew Member only sees their own
  // assignments. Crew profile/skills/availability stay CLI-only (out of
  // scope for this showcase — see PRD §10 #16-18).
  if (user.role === "crew_member") {
    return <CrewSection />;
  }
  return <MissionsSection />;
}
