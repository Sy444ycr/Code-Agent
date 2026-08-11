import { useState } from "react";

import { TaskForm } from "./components/TaskForm";
import type { TaskDetail } from "./types";

export default function App() {
  const [task, setTask] = useState<TaskDetail | null>(null);

  return (
    <main>
      <h1>Code-Agent Task Console</h1>
      <TaskForm onCreated={setTask} />
      <section aria-label="timeline">{task ? task.id : "No active task"}</section>
    </main>
  );
}
