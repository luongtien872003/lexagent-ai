import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      // ── Colors ─────────────────────────────────────
      colors: {
        bg: {
          base: "#0c0c0d",
          1:    "#111113",
          2:    "#17171a",
          3:    "#1d1d21",
          4:    "#242428",
        },
        line: {
          DEFAULT: "rgba(255,255,255,0.048)",
          2:       "rgba(255,255,255,0.08)",
          3:       "rgba(255,255,255,0.12)",
        },
        ink: {
          0: "#e8e8ea",
          1: "#9090a0",
          2: "#52525e",
          3: "#303038",
        },
        gold: {
          DEFAULT: "#b8906a",
          dim:     "rgba(184,144,106,0.10)",
          border:  "rgba(184,144,106,0.20)",
          glow:    "rgba(184,144,106,0.06)",
          text:    "#c49870",
        },
        ok: {
          DEFAULT: "#4a9966",
          dim:     "rgba(74,153,102,0.10)",
        },
        cite: {
          amber:         "rgba(184,144,106,0.11)",
          "amber-text":  "#c49870",
          "amber-line":  "rgba(184,144,106,0.20)",
          green:         "rgba(74,153,102,0.10)",
          "green-text":  "#569970",
          "green-line":  "rgba(74,153,102,0.18)",
          blue:          "rgba(88,138,208,0.10)",
          "blue-text":   "#6898cc",
          "blue-line":   "rgba(88,138,208,0.18)",
          purple:         "rgba(166,108,188,0.09)",
          "purple-text":  "#ae78c0",
          "purple-line":  "rgba(166,108,188,0.16)",
        },
      },

      // ── Typography ──────────────────────────────────
      fontFamily: {
        serif: ["var(--font-serif)", "Georgia", "serif"],
        sans:  ["var(--font-sans)",  "system-ui", "sans-serif"],
        mono:  ["var(--font-mono)",  "Menlo", "monospace"],
      },

      fontSize: {
        "tag":        ["9px",    { lineHeight: "1.3",  letterSpacing: "0.06em"  }],
        "sup":        ["8.5px",  { lineHeight: "1",    letterSpacing: "0"       }],
        "2xs":        ["10px",   { lineHeight: "1.4",  letterSpacing: "0.08em"  }],
        "mono-label": ["11px",   { lineHeight: "1.4",  letterSpacing: "0.005em" }],
        "xs":         ["11.5px", { lineHeight: "1.45", letterSpacing: "0.01em"  }],
        "sm":         ["12.5px", { lineHeight: "1.5",  letterSpacing: "0"       }],
        "base":       ["14px",   { lineHeight: "1.55", letterSpacing: "-0.01em" }],
        "body":       ["13.5px", { lineHeight: "1.78", letterSpacing: "-0.005em"}],
        "md":         ["15px",   { lineHeight: "1.72", letterSpacing: "-0.01em" }],
        "lg":         ["16px",   { lineHeight: "1.5",  letterSpacing: "-0.015em"}],
        "xl":         ["18px",   { lineHeight: "1.4",  letterSpacing: "-0.02em" }],
        "2xl":        ["24px",   { lineHeight: "1.25", letterSpacing: "-0.025em"}],
        "3xl":        ["36px",   { lineHeight: "1.15", letterSpacing: "-0.03em" }],
      },

      // ── Radius ──────────────────────────────────────
      borderRadius: {
        xs:    "3px",
        sm:    "5px",
        md:    "7px",
        lg:    "10px",
        xl:    "14px",
        "2xl": "18px",
        full:  "9999px",
      },

      // ── Layout ──────────────────────────────────────
      width: {
        sidebar: "232px",
        source:  "380px",
      },

      // ── Transitions ─────────────────────────────────
      transitionTimingFunction: {
        spring: "cubic-bezier(0.16, 1, 0.3, 1)",
        smooth: "cubic-bezier(0.4, 0, 0.2, 1)",
      },
      transitionDuration: {
        "60":  "60ms",
        "100": "100ms",
        "150": "150ms",
        "200": "200ms",
        "300": "300ms",
      },

      // ── Animations ──────────────────────────────────
      keyframes: {
        "pulse-dot": {
          "0%, 100%": { opacity: "1",    transform: "scale(1)"    },
          "50%":      { opacity: "0.25", transform: "scale(0.65)" },
        },
        "blink": {
          "0%, 100%": { opacity: "1" },
          "50%":      { opacity: "0" },
        },
        "thinking-dot": {
          "0%, 60%, 100%": { transform: "translateY(0)",      opacity: "0.3" },
          "30%":           { transform: "translateY(-2.5px)", opacity: "1"   },
        },
        "fade-up": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to:   { opacity: "1", transform: "translateY(0)"   },
        },
        "fade-in-text": {
          // New: phrase-level fade-in for streaming text chunks
          from: { opacity: "0" },
          to:   { opacity: "1" },
        },
        "slide-in": {
          from: { opacity: "0", transform: "translateX(4px)" },
          to:   { opacity: "1", transform: "translateX(0)"   },
        },
        "shimmer": {
          // New: skeleton loading shimmer
          "0%":   { opacity: "0.3" },
          "50%":  { opacity: "0.7" },
          "100%": { opacity: "0.3" },
        },
        "scale-in": {
          // New: for tooltip and panel appear
          from: { opacity: "0", transform: "scale(0.97) translateY(4px)" },
          to:   { opacity: "1", transform: "scale(1)    translateY(0)"   },
        },
      },
      animation: {
        "pulse-dot":       "pulse-dot 1.2s ease-in-out infinite",
        "blink":           "blink 0.9s step-end infinite",
        "thinking-dot":    "thinking-dot 1.5s ease-in-out infinite",
        "thinking-dot-2":  "thinking-dot 1.5s ease-in-out 0.18s infinite",
        "thinking-dot-3":  "thinking-dot 1.5s ease-in-out 0.36s infinite",
        "fade-up":         "fade-up 220ms cubic-bezier(0.16,1,0.3,1) both",
        "fade-in-text":    "fade-in-text 160ms ease-out both",
        "slide-in":        "slide-in 180ms cubic-bezier(0.16,1,0.3,1) both",
        "shimmer":         "shimmer 1.4s ease-in-out infinite",
        "scale-in":        "scale-in 180ms cubic-bezier(0.16,1,0.3,1) both",
      },
    },
  },
  plugins: [],
};

export default config;
