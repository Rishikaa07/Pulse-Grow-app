import type { Config } from "tailwindcss";

/**
 * The palette is deliberately narrow. One accent (electric cyan) carries every
 * "this deserves your attention" signal; direction is carried by muted mint and
 * rose used at text weight only, never as filled pills — a wall of green and red
 * blocks is the thing this product exists to replace.
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        void: "#06070A",
        surface: "#0A0C11",
        raised: "#0F1218",
        line: "rgba(255,255,255,0.07)",
        "line-strong": "rgba(255,255,255,0.14)",
        ink: "#EDEFF3",
        "ink-2": "#949BA8",
        "ink-3": "#5B626F",
        "ink-4": "#3A404B",
        accent: "#5CE1FF",
        "accent-deep": "#1B8FB0",
        indigo: "#7C7BFF",
        up: "#63D8A4",
        down: "#FF8A97",
      },
      fontFamily: {
        sans: [
          "ui-sans-serif",
          "-apple-system",
          "BlinkMacSystemFont",
          "Inter",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "SF Mono",
          "JetBrains Mono",
          "Menlo",
          "monospace",
        ],
      },
      fontSize: {
        display: ["clamp(2.6rem, 5.5vw, 4.25rem)", { lineHeight: "1.02", letterSpacing: "-0.035em" }],
        title: ["clamp(1.65rem, 2.6vw, 2.35rem)", { lineHeight: "1.1", letterSpacing: "-0.025em" }],
        heading: ["1.125rem", { lineHeight: "1.3", letterSpacing: "-0.012em" }],
        micro: ["0.6875rem", { lineHeight: "1.45", letterSpacing: "0.02em" }],
      },
      transitionTimingFunction: {
        pulse: "cubic-bezier(0.22, 1, 0.36, 1)",
      },
      keyframes: {
        "score-in": {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "node-pulse": {
          "0%, 100%": { opacity: "0", transform: "scale(1)" },
          "45%": { opacity: "0.55", transform: "scale(2.1)" },
        },
        "panel-in": {
          "0%": { opacity: "0", transform: "translateX(24px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        "fade-in": { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
        shimmer: { "100%": { transform: "translateX(100%)" } },
      },
      animation: {
        "score-in": "score-in 0.5s cubic-bezier(0.22,1,0.36,1) both",
        "node-pulse": "node-pulse 3.2s ease-out infinite",
        "panel-in": "panel-in 0.32s cubic-bezier(0.22,1,0.36,1) both",
        "fade-in": "fade-in 0.4s ease both",
      },
    },
  },
  plugins: [],
};

export default config;
