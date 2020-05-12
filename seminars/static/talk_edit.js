// Adapted from the LMFDB's knowl_edit.js

/* parameters */
var all_modes = ['preview'];
var REFRESH_TIMEOUT = 2000;
/* state flags */
var refresh_id    = null;
var reparse_latex = false;
var unsaved = false;

function refresh_preview() {
  var $title = $("#view-title");
  var $kcontent = $("#inp_abstract");
  var $content = $("#view-abstract");
  var $refresh = $("#refresh-view");
  $title.html("Processing ...");
  var pkcontent = '';
  var pkcontent = "";
  $kcontent.val().split('\n\n').forEach(
    paragraph => pkcontent += "<p>" + paragraph + "</p>"
  );
  $content.html(pkcontent);
  renderMathInElement($content.get(0), katexOpts);
  refresh_id = null;
  // once rendering is done.
  // has there been a call in the meantime and we have to do this again?
  if (reparse_latex) {
    /* console.log("reparse_latex == true"); */
    reparse_latex = false;
    view_refresh();
  }
  /* finally, set the title and hide the refresh link */
  $title.html($("#inp_title").val());
  renderMathInElement($title.get(0), katexOpts); // render any math in the title
  $refresh.fadeOut();
}

/* if nothing scheduled, refresh delayed
   otherwise tell it to reparse the latex */
function delay_refresh() {
  unsaved = true;
  $("#refresh-view").fadeIn();
  if (refresh_id) {
    reparse_latex = true;
  } else {
    refresh_id = window.setTimeout(view_refresh, REFRESH_TIMEOUT);
  }
}

function view_refresh() {
  if (refresh_id) {
    /* this case happens, when we click "refresh" while a timer is running. */
    window.clearTimeout(refresh_id);
  }
  refresh_preview();
  $('#refresh-view').hide();
}

