import { useState } from "react";

export default function App() {
  const [goal, setGoal] = useState("");
  const [error, setError] = useState("");
  return <main><h1>Code-Agent Task Console</h1><label>Workspace<input aria-label="workspace" defaultValue="." /></label><label>Goal<input aria-label="goal" value={goal} onChange={event => setGoal(event.target.value)} /></label><button onClick={() => setError(goal.trim() ? "" : "Goal is required")}>Start Task</button>{error && <p role="alert">{error}</p>}<section aria-label="timeline">No active task</section></main>;
}
