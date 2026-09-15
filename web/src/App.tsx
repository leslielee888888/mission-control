import { useState } from "react";
import { useAuth } from "./auth/AuthContext";
import { LoginScreen } from "./screens/LoginScreen";
import { MissionListScreen } from "./screens/MissionListScreen";
import { MissionCreateScreen } from "./screens/MissionCreateScreen";
import { MissionDetailScreen } from "./screens/MissionDetailScreen";
import { MyAssignmentsScreen } from "./screens/MyAssignmentsScreen";
import { CrewListScreen } from "./screens/CrewListScreen";
import { CrewProfileScreen } from "./screens/CrewProfileScreen";
import { SkillsScreen } from "./screens/SkillsScreen";
import { MyProfileScreen } from "./screens/MyProfileScreen";
import {
  AssignmentsNavIcon,
  CrewNavIcon,
  MissionsNavIcon,
  ProfileNavIcon,
  Sidebar,
  SkillsNavIcon,
  type NavItem,
} from "./components/Sidebar";
import { Spinner } from "./components/Spinner";

type DirectorLeadSection = "missions" | "crew" | "skills";

const DIRECTOR_LEAD_NAV: NavItem[] = [
  { key: "missions", label: "Missions", icon: MissionsNavIcon },
  { key: "crew", label: "Crew", icon: CrewNavIcon },
  { key: "skills", label: "Skills", icon: SkillsNavIcon },
];

/** Director / Mission Lead: Missions (existing), Crew (roster -> read-only
 * profile, FR-4), Skills (org taxonomy, FR-5). No router — each is a
 * sibling top-level section, and within Missions/Crew a `useState` stack
 * two screens deep at most (PRD §7: "no routing depth"). */
function DirectorLeadApp() {
  const [section, setSection] = useState<DirectorLeadSection>("missions");
  const [selectedMissionId, setSelectedMissionId] = useState<number | null>(null);
  const [isCreatingMission, setIsCreatingMission] = useState(false);
  const [selectedCrewId, setSelectedCrewId] = useState<number | null>(null);

  function selectSection(key: string) {
    setSection(key as DirectorLeadSection);
    // Leaving a section resets its drill-down so coming back starts at the list.
    setSelectedMissionId(null);
    setIsCreatingMission(false);
    setSelectedCrewId(null);
  }

  let content;
  if (section === "missions") {
    if (isCreatingMission) {
      content = (
        <MissionCreateScreen
          onCreated={(missionId) => {
            setIsCreatingMission(false);
            setSelectedMissionId(missionId);
          }}
          onCancel={() => setIsCreatingMission(false)}
        />
      );
    } else if (selectedMissionId === null) {
      content = (
        <MissionListScreen onSelectMission={setSelectedMissionId} onCreateMission={() => setIsCreatingMission(true)} />
      );
    } else {
      content = <MissionDetailScreen missionId={selectedMissionId} onBack={() => setSelectedMissionId(null)} />;
    }
  } else if (section === "crew") {
    content =
      selectedCrewId === null ? (
        <CrewListScreen onSelectCrew={setSelectedCrewId} />
      ) : (
        <CrewProfileScreen crewId={selectedCrewId} onBack={() => setSelectedCrewId(null)} />
      );
  } else {
    content = <SkillsScreen />;
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar items={DIRECTOR_LEAD_NAV} activeKey={section} onSelect={selectSection} />
      {content}
    </div>
  );
}

type CrewMemberSection = "assignments" | "profile";

const CREW_MEMBER_NAV: NavItem[] = [
  { key: "assignments", label: "My assignments", icon: AssignmentsNavIcon },
  { key: "profile", label: "My profile", icon: ProfileNavIcon },
];

/** Crew Member: My Assignments (existing) + My Profile (new: self-service
 * profile/skills/availability, FR-4/FR-6/FR-7). */
function CrewMemberApp() {
  const [section, setSection] = useState<CrewMemberSection>("assignments");

  return (
    <div className="flex min-h-screen">
      <Sidebar items={CREW_MEMBER_NAV} activeKey={section} onSelect={(key) => setSection(key as CrewMemberSection)} />
      {section === "assignments" ? <MyAssignmentsScreen /> : <MyProfileScreen />}
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

  // Role-conditional nav off the logged-in user's role (§10 #23, extended
  // for T8b): Director/Mission Lead get Missions/Crew/Skills; Crew Member
  // gets My Assignments/My Profile. Explicitly allow-listing the privileged
  // roles (rather than "anything that isn't crew_member") means a missing
  // or unrecognized role falls through to the login screen, not the
  // privileged app — belt-and-suspenders alongside the API's own
  // server-side RBAC, which is the actual enforcement boundary.
  if (user.role === "director" || user.role === "mission_lead") {
    return <DirectorLeadApp />;
  }
  if (user.role === "crew_member") {
    return <CrewMemberApp />;
  }
  return <LoginScreen />;
}
