/* §2 Methodology: the lead paragraph only; content/index.js attaches §2.1-2.4.
 * Content model and rules: data/dev/design/methodology/brief.md. */

export default {
  id: 'sec-methods',
  title: 'Methodology',
  blocks: [
    { kind: 'p', text: String.raw`This section states what the service computes before anything is drawn. [[sec-frames]] defines the four reference frames and the rigid motions that co-register events and showers; [[sec-discretisation]] the binning of an irregular, staggered lattice and of co-registered hits, and the conservative kernels that reconstruct a display field from the bins; [[sec-attribution]] the networks' attribution channels and how they are summed and signed; and [[sec-statistics]] the estimators, their intervals and the sample-size gates that decide which of them a panel may report and which it may draw. Two principles run through all four. Every operator is stated as the code applies it, with its file named, and every number the prose quotes, a gate, a width, a window or a threshold, is the code's own constant, read from it and listed with its source in Appendix B ([[app-constants]]). Measured figures are a different kind of number: they are cited with the dataset they were measured on, as the evidence that fixed a design choice.` },
  ],
};
