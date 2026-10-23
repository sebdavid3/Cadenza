// Iconos dibujados en una rejilla de 8×8 píxeles, del mismo grano que la tipografía bitmap.
// Cada cadena es una fila; «#» es un píxel de tinta.
const GLYPHS = {
  "arrow-right": [
    "....#...",
    ".....#..",
    "......#.",
    "########",
    "......#.",
    ".....#..",
    "....#...",
  ],
  "arrow-left": [
    "...#....",
    "..#.....",
    ".#......",
    "########",
    ".#......",
    "..#.....",
    "...#....",
  ],
  download: [
    "...##...",
    "...##...",
    "...##...",
    "########",
    ".######.",
    "..####..",
    "...##...",
    "########",
  ],
} satisfies Record<string, string[]>;

export type PixelIconName = keyof typeof GLYPHS;

function toPath(rows: string[]): string {
  let path = "";
  rows.forEach((row, y) => {
    for (let x = 0; x < row.length; x += 1) {
      if (row.charAt(x) === "#") path += `M${x} ${y}h1v1h-1z`;
    }
  });
  return path;
}

export function PixelIcon({ name, className }: { name: PixelIconName; className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 8 8"
      width="1em"
      height="1em"
      fill="currentColor"
      shapeRendering="crispEdges"
      aria-hidden="true"
      focusable="false"
    >
      <path d={toPath(GLYPHS[name])} />
    </svg>
  );
}
