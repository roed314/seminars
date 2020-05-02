katexOpts = {
  delimiters: [
  {left: "$$", right: "$$", display: true},
  {left: "\\[", right: "\\]", display: true},
  {left: "$", right: "$", display: false},
  {left: "\\(", right: "\\)", display: false}
  ],
  macros: {
  "\\C": '{\\mathbb{C}}',
  "\\R": '{\\mathbb{R}}',
  "\\Q": '{\\mathbb{Q}}',
  "\\Z": '{\\mathbb{Z}}',
  "\\F": '{\\mathbb{F}}',
  "\\H": '{\\mathbb{H}}',
  "\\HH": '{\\mathcal{H}}',
  "\\integers": '{\\mathcal{O}}',
  "\\SL": '{\\textrm{SL}}',
  "\\GL": '{\\textrm{GL}}',
  "\\PSL": '{\\textrm{PSL}}',
  "\\PGL": '{\\textrm{PGL}}',
  "\\Sp": '{\\textrm{Sp}}',
  "\\GSp": '{\\textrm{GSp}}',
  "\\PSp": '{\\textrm{PSp}}',
  "\\PSU": '{\\textrm{PSU}}',
  "\\Gal": '{\\mathop{\\rm Gal}}',
  "\\Aut": '{\\mathop{\\rm Aut}}',
  "\\Sym": '{\\mathop{\\rm Sym}}',
  "\\End": '{\\mathop{\\rm End}}',
  "\\Reg": '{\\mathop{\\rm Reg}}',
  "\\Ord": '{\\mathop{\\rm Ord}}',
  "\\sgn": '{\\mathop{\\rm sgn}}',
  "\\trace": '{\\mathop{\\rm trace}}',
  "\\Res": '{\\mathop{\\rm Res}}',
  "\\mathstrut": '\\vphantom(',
  "\\ideal": '{\\mathfrak{ #1 }}',
  "\\classgroup": '{Cl(#1)}',
  "\\modstar": '{\\left( #1/#2 \\right)^\\times}',
  },
};
document.addEventListener("DOMContentLoaded", function() {
  renderMathInElement(document.body, katexOpts);
});
