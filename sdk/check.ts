/// <reference path="./ephe.d.ts" />

export async function check(): Promise<void> {
  const value: unknown = await ephe.storage.get("note");
  await ephe.storage.set("note", { n: 1 });
  const text: string = await ephe.callTool("tick", { unit: "s" });
  const stop: () => void = ephe.subscribe((event) => {
    const name: string = event.event;
    const body: unknown = event.data;
    void name;
    void body;
  });
  stop();
  void value;
  void text;
}
