import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export default function NewRunPage() {
  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-normal">New run</h1>
      <Tabs defaultValue="template" className="mt-6">
        <TabsList>
          <TabsTrigger value="template">Template</TabsTrigger>
          <TabsTrigger value="code">Code</TabsTrigger>
          <TabsTrigger value="math">Math</TabsTrigger>
        </TabsList>
        <TabsContent value="template" className="rounded-lg border p-6">
          Template picker foundation
        </TabsContent>
        <TabsContent value="code" className="rounded-lg border p-6">
          Code input foundation
        </TabsContent>
        <TabsContent value="math" className="rounded-lg border p-6">
          Math input foundation
        </TabsContent>
      </Tabs>
    </div>
  );
}
