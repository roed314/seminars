function embed_schedule(){
function load_data() {
  console.log("load_data");
  $.each($('.embeddable_schedule'), function(i, div) {
    var shortname = div.getAttribute('shortname');
    var daterange = div.getAttribute('daterange');
    var url = "{{ url_for('show_seminar_json', shortname='_SHORTNAME_', _external=True, _scheme=scheme) }}".replace('_SHORTNAME_', shortname) ;
    var display_knowl = div.getAttribute('noabstract') === null;
    console.log(display_knowl);
    var display_header = div.getAttribute('noheader') === null;
    if (div.getAttribute('format')) {
      var format = div.getAttribute('format');
    } else {
      var format = 'MMMM D, hh:mm';
    }
    console.log(url);
    console.log(daterange);
    $.ajax({
      type: "GET",
      url: url,
      data: {'daterange' : daterange},
      async: false,
      dataType: 'jsonp',
      crossDomain: true}).done(
        //success:
        function( data ) {
          console.log("calling call");
          // build header
          table = document.createElement('table');
          if( display_header ) {
            thead = document.createElement('thead')
            row = document.createElement('tr');
            col = document.createElement('th');
            col.textContent = "Time";
            row.appendChild(col);
            col = document.createElement('th');
            col.textContent = "Speaker";
            row.appendChild(col);
            col = document.createElement('th')
            col.textContent = "Title";
            row.appendChild(col);
            thead.appendChild(row);
            table.appendChild(thead);
          }
          // build the rest of the table
          tbody = document.createElement('tbody');
          $.each( data, function( i, item ) {
            row = document.createElement('tr');
            col = document.createElement('td');
            col.textContent = moment(item.start_time).format(format);
            row.appendChild(col);
            col = document.createElement('td');
            if( item.speaker_homepage ) {
              a = document.createElement('a')
              a.href = item.speaker_homepage;
              a.textContent = item.speaker;
              col.appendChild(a);
            } else {
              span = document.createElement('span');
              span.textContent = item.speaker;
              col.appendChild(span);
            }
            if( item.speaker_affiliation ) {
              span = document.createElement('span');
              span.textContent = ' (' + item.speaker_affiliation + ')';
              col.appendChild(span);
            }
            row.appendChild(col);
            col = document.createElement('td');
            if( display_knowl &&  item.abstract) {
              a = document.createElement('a');
              a.title = item.title;
              a.textContent = item.title;
              a.setAttribute('knowl', 'dynamic_show');
              a.href = '#';
              var kwargs = "<div>";
              item.abstract.split('\n\n').forEach(
                paragraph => kwargs += "<p>" + paragraph + "</p>"
              );
              kwargs += "</div>";
              a.setAttribute("kwargs", kwargs);
              col.appendChild(a);
            } else {
              col.textContent = item.title;
            }
            row.appendChild(col);
            tbody.appendChild(row);
          }
          )
          table.appendChild(tbody);
          div.appendChild(table);
        });
  });
  knowl();
}

function knowl() {
  /**
   * https://github.com/component/debounce
   * Returns a function, that, as long as it continues to be invoked, will not
   * be triggered. The function will be called after it stops being called for
   * N milliseconds. If `immediate` is passed, trigger the function on the
   * leading edge, instead of the trailing. The function also has a property 'clear' 
   * that is a function which will clear the timer to prevent previously scheduled executions. 
   *
   * Copyright (c) 2009-2018 Jeremy Ashkenas, DocumentCloud and Investigative
   * Reporters & Editors
   *
   * Permission is hereby granted, free of charge, to any person
   * obtaining a copy of this software and associated documentation
   * files (the "Software"), to deal in the Software without
   * restriction, including without limitation the rights to use,
   * copy, modify, merge, publish, distribute, sublicense, and/or sell
   * copies of the Software, and to permit persons to whom the
   * Software is furnished to do so, subject to the following
   * conditions:
   *
   * The above copyright notice and this permission notice shall be
   * included in all copies or substantial portions of the Software.
   *
   * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
   * EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
   * OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
   * NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
   * HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
   * WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
   * FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
   * OTHER DEALINGS IN THE SOFTWARE.
   */
  function debounce(func, wait, immediate){
    var timeout, args, context, timestamp, result;
    if (null == wait) wait = 100;

    function later() {
      var last = Date.now() - timestamp;

      if (last < wait && last >= 0) {
        timeout = setTimeout(later, wait - last);
      } else {
        timeout = null;
        if (!immediate) {
          result = func.apply(context, args);
          context = args = null;
        }
      }
    };

    var debounced = function(){
      context = this;
      args = arguments;
      timestamp = Date.now();
      var callNow = immediate && !timeout;
      if (!timeout) timeout = setTimeout(later, wait);
      if (callNow) {
        result = func.apply(context, args);
        context = args = null;
      }

      return result;
    };

    debounced.clear = function() {
      if (timeout) {
        clearTimeout(timeout);
        timeout = null;
      }
    };

    debounced.flush = function() {
      if (timeout) {
        result = func.apply(context, args);
        context = args = null;

        clearTimeout(timeout);
        timeout = null;
      }
    };

    return debounced;
  };
  /* javascript code for the knowledge db features */
  /* global counter, used to uniquely identify each knowl-output element
   * that's necessary because the same knowl could be referenced several times
   * on the same page */
  var knowl_id_counter = 0;
  /* site wide cache, TODO html5 local storage to cover whole domain
   * /w a freshness timeout of about 10 minutes */
  var knowl_cache = {};

  //something like this should work:
  //parseInt($('.knowl-output').css('border-left-width')) + parseInt($('.knowl-output').css('margin'));
  var table_border_knowl_width = 20;
  function knowl_click_handler($el) {
    // the knowl attribute holds the id of the knowl
    var knowl_id = $el.attr("knowl");
    // the uid is necessary if we want to reference the same content several times
    var uid = $el.attr("knowl-uid");
    var output_id = '#knowl-output-' + uid;
    var $output_id = $(output_id);

    // slightly different behaviour if we are inside a table, but
    // not in a knowl inside a table.
    var table_mode = $el.parent().is("td") || $el.parent().is("th");

    // if we already have the content, toggle visibility
    if ($output_id.length > 0) {
      if (table_mode) {
        $output_id.parent().parent().slideToggle("fast");
      }
      $output_id.slideToggle("fast");
      $el.toggleClass("active");

      // otherwise download it or get it from the cache
    } else {
      $el.addClass("active");
      // create the element for the content, insert it after the one where the
      // knowl element is included (e.g. inside a <h1> tag) (sibling in DOM)
      var idtag = "id='"+output_id.substring(1) + "'";

      // behave a bit differently, if the knowl is inside a td or th in a table.
      // otherwise assume its sitting inside a <div> or <p>
      if(table_mode) {
        // assume we are in a td or th tag, go 2 levels up
        var td_tag = $el.parent();
        var tr_tag = td_tag.parent();
        var div = $el.parent().parent().parent();

        // figure out max_width
        var row_width = tr_tag.width();
        var sidebar = document.getElementById("sidebar");
        if ( sidebar == undefined ) {
          var sibebar_width = 0;
        } else {
          var sibebar_width = sidebar.offsetWidth;
        }
        header = document.getElementById("header")
        if ( header == undefined ) {
          var header_width = row_width;
        } else {
          var header_width = header.offsetWidth;
        }
        var desired_main_width =  header_width - sibebar_width;
        console.log("row_width: " + row_width);
        console.log("desired_main_width: " + desired_main_width);
        // no larger than the current row width (for normal tables)
        // no larger than the desired main width (for extra large tables)
        // at least 700px (for small tables)
        // and deduce margins and borders
        var margins_and_borders = 2*table_border_knowl_width + parseInt(td_tag.css('padding-left')) + parseInt(td_tag.css('padding-right'))
        var max_width = Math.max(700, Math.min(row_width, desired_main_width)) - margins_and_borders;

        console.log("max_width: " + max_width);
        var style_wrapwidth = "style='max-width: " + max_width + "px; white-space: normal;'";

        //max rowspan of this row
        var max_rowspan = Array.from(tr_tag.children()).reduce((acc, td) => Math.max(acc, td.rowSpan), 0)
        console.log("max_rowspan: " + max_rowspan);

        //compute max number of columns in the table
        var cols = Array.from(tr_tag.children()).reduce((acc, td) => acc + td.colSpan, 0)
        cols = Array.from(tr_tag.siblings("tr")).reduce((ac, tr) => Math.max(ac, Array.from(tr.children).reduce((acc, td) => acc + td.colSpan, 0)), cols);
        console.log("cols: " + cols);
        for (var i = 0; i < max_rowspan-1; i++)
          tr_tag = tr_tag.next();
        tr_tag.after(
          "<tr><td colspan='"+cols+"'><div class='knowl-output'" +idtag+ style_wrapwidth + ">loading '"+knowl_id+"' …</div></td></tr>");
        // For alternatinvg color tables
        tr_tag.after("<tr class='hidden'></tr>")
      } else {
        $el.parent().after("<div class='knowl-output'" +idtag+ ">loading '"+knowl_id+"' …</div>");
      }

      // "select" where the output is and get a hold of it
      var $output = $(output_id);
      var kwargs = $el.attr("kwargs");

      console.log("dynamic_show: " + kwargs);
      $output.html('<div class="knowl"><div><div class="knowl-content">' + kwargs + '</div></div></div>');
      // Support for escaping html within a div inside the knowl
      // Used for code references in showing knowls
      var pretext = $el.attr("pretext");
      console.log("pretext: " + pretext);
      if (typeof pretext !== typeof undefined && pretext !== false) {
        $output.find("pre").text(pretext);
      }
      try
      {
        renderMathInElement($output.get(0), katexOpts);
      }
      catch(err) {
        console.log("err:" + err)
      }
      $output.slideDown("slow");
      // adjust width to assure that every katex block is inside of the knowl
      var knowl = document.getElementById(output_id.substring(1))
      var new_width = Array.from(knowl.getElementsByClassName("katex")).reduce((acc, elt) => Math.max(acc, elt.offsetWidth), 0) + margins_and_borders;
      console.log("new_width:" + new_width)
      if( new_width > max_width ) {
        console.log("setting maxWidth:" + new_width)
        knowl.style.maxWidth = new_width + "px";
      }
    }
  } //~~ end click handler for *[knowl] elements

  /** register a click handler for each element with the knowl attribute
   * @see jquery's doc about 'live'! the handler function does the
   *  download/show/hide magic. also add a unique ID,
   *  necessary when the same reference is used several times. */
  function knowl_handle(evt) {
    evt.preventDefault();
    var $knowl = $(this);
    if(!$knowl.attr("knowl-uid")) {
      console.log("knowl-uid = " + knowl_id_counter);
      $knowl.attr("knowl-uid", knowl_id_counter);
      knowl_id_counter++;
    }
    knowl_click_handler($knowl, evt);
  }
  $(function() {
    $("body").on("click", "*[knowl]", debounce(knowl_handle,500, true));
  });
};

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



var headTag = document.getElementsByTagName("head")[0];
var jqTag = document.createElement('script');
jqTag.type = 'text/javascript';
jqTag.src = 'https://ajax.googleapis.com/ajax/libs/jquery/3.1.0/jquery.min.js';
headTag.appendChild(jqTag);


var katexcssTag = document.createElement('link');
katexcssTag.rel = "stylesheet";
katexcssTag.href = "https://cdn.jsdelivr.net/npm/katex@0.11.1/dist/katex.css";
headTag.appendChild(katexcssTag);

var katexTag = document.createElement('script');
katexTag.type = 'text/javascript';
katexTag.src = 'https://cdn.jsdelivr.net/npm/katex@0.11.1/dist/katex.js';
katexTag.defer = '';
headTag.appendChild(katexTag);

var mTag = document.createElement('script');
mTag.type = 'text/javascript';
mTag.src = "{{ url_for('static', filename='daterangepicker/moment.min.js', _external=True, _scheme=scheme) }}";
headTag.appendChild(mTag);

function defer(method) {
  if (window.jQuery && window.katex ) {
    method();
  } else {
    setTimeout(function() { defer(method) }, 10);
  }
}

defer(function() {
  var katex2Tag = document.createElement('script');
  katex2Tag.type = 'text/javascript';
  katex2Tag.src = 'https://cdn.jsdelivr.net/npm/katex@0.11.1/dist/contrib/auto-render.js';
  katex2Tag.defer = '';
  headTag.appendChild(katex2Tag);
});
defer(function() {document.addEventListener("DOMContentLoaded", function() { renderMathInElement(document.body, katexOpts); });});
defer(load_data);
};
