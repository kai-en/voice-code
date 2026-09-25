// M6.1 voice-end: 让 LLM 主动结束语音会话的退出工具（v2.0.16 插件，零 import 写法）
// 部署位置: tools/oc2-home/config/opencode/plugins/voice-end.ts（全局 plugins 目录自动发现）
// 要点: options.codemode:false 必须显式，否则被折叠进 CodeMode 小模型无法直调。
export default {
  id: "voice-end",
  async setup(ctx: any) {
    await ctx.tool.transform((editor: any) => {
      editor.add({
        name: "voice-end",
        description:
          "End the current voice session. This is the ONLY way to end it. When the " +
          "user says goodbye or asks to end/exit the conversation, you MUST call " +
          "this tool FIRST, before writing any goodbye text. After the call, say one " +
          "short friendly goodbye and stop.",
        input: {
          type: "object",
          properties: {
            reason: { type: "string", description: "e.g. user-said-goodbye" },
          },
          additionalProperties: false,
        },
        options: { codemode: false },
        execute: async (_input: any) => ({
          content:
            "Voice session is ending. Say one short friendly goodbye now, " +
            "then stop. Do not call any more tools.",
        }),
      })
    })
  },
}
