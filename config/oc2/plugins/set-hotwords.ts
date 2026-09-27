// M14 set-hotwords: 让 LLM 把当前话题的专有名词装填进 ASR 热词表（v2.0.16 插件，零 import 写法）
// 部署位置: tools/oc2-home/config/opencode/plugins/set-hotwords.ts；execute 纯静态返回，
// 主进程从 SSE 的 tool.called 帧旁观取 input.words 完成真实装填（与 voice-end 同构）。
export default {
  id: "set-hotwords",
  async setup(ctx: any) {
    await ctx.tool.transform((editor: any) => {
      editor.add({
        name: "set-hotwords",
        description:
          "Replace the live ASR hotword table for the current topic. Call this BEFORE " +
          "answering when the matched wow-kb entry has a `hotwords:` field — pass that " +
          "list verbatim (max 8 words). Call with an empty list when switching to a " +
          "topic whose entry has no hotwords. NEVER invent, add, or drop words on your " +
          "own. This only biases speech recognition; it does not end or pause anything.",
        input: {
          type: "object",
          properties: {
            words: {
              type: "array",
              items: { type: "string" },
              maxItems: 8,
              description: "exact copy of the entry's hotwords list; [] to clear",
            },
          },
          additionalProperties: false,
        },
        options: { codemode: false },
        execute: async (_input: any) => ({
          content: "Hotwords received. Continue answering now.",
        }),
      })
    })
  },
}
