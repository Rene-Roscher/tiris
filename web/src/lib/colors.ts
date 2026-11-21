/** Device colours: slot 1..6 from the validated categorical palette (--chart-N), 0 = "other". Same colour on every view. */
export const slotVar = (slot: number | null | undefined) => (slot && slot >= 1 && slot <= 6 ? `var(--chart-${slot})` : 'var(--chart-other)')
