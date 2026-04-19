// Sitting 9 — Main dashboard page scaffold
import UploadSection from "../components/UploadSection";
import RoadmapDisplay from "../components/RoadmapDisplay";
import SkillGraph from "../components/SkillGraph";

export default function Dashboard() {
  return (
    <main>
      <UploadSection />
      <RoadmapDisplay />
      <SkillGraph />
    </main>
  );
}
