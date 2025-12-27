import { PageShell } from "@/components/app/page-shell";
import { ProjectList } from "@/components/projects/project-list";

export default function HomePage() {
  return (
    <PageShell
      title="项目"
      subtitle="管理工程、导入简谱、进入编辑器。工程列表来自后端 workspace。"
    >
      <ProjectList />
    </PageShell>
  );
}
