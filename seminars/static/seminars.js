
function toggle_time() {
    var future = $('#future_talks');
    var past = $('#past_talks');
    if (future.is(":visible"))
    {
        future.hide();
        past.show();
    } else {
        past.hide();
        future.show();
    }
}

function setCookie(name,value) {
    document.cookie = name + "=" + (value || "") + ";path=/";
}
function getCookie(name) {
    var nameEQ = name + "=";
    var ca = document.cookie.split(';');
    for(var i=0;i < ca.length;i++) {
        var c = ca[i];
        while (c.charAt(0)==' ') c = c.substring(1,c.length);
        if (c.indexOf(nameEQ) == 0) return c.substring(nameEQ.length,c.length);
    }
    return null;
}
function eraseCookie(name) {
    document.cookie = name+'=; Max-Age=-99999999;';
}
const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
setCookie("browser_timezone", tz);
function addCategory(cat) {
    var cur_cats = getCookie("categories");
    if (cur_cats) {
        cur_cats = cur_cats + "," + cat;
    } else {
        cur_cats = cat;
    }
    setCookie("categories", cur_cats);
}
function removeCategory(cat) {
    var cur_cats = getCookie("categories");
    cur_cats = cur_cats.replace(cat, "").replace(",,",",");
    setCookie("categories", cur_cats);
}

function setCategoryLinks() {
    var cur_cats = getCookie("categories")
    console.log(cur_cats);
    if (cur_cats == null) {
        cur_cats = "ALL";
        setCookie("categories", "ALL");
    }
    cur_cats = cur_cats.split(",");
    for (var i=0; i<cur_cats.length; i++) {
        $("#catlink-" + cur_cats[i]).addClass("catselected");
        $(".cat-" + cur_cats[i]).removeClass("catunselected");
    }
}
function toggleCategory(id) {
    var toggler = $("#" + id);
    var cat = id.substring(8);
    console.log(cat);
    if (toggler.hasClass("catselected")) {
        toggler.removeClass("catselected");
        removeCategory(cat);
        $(".cat-" + cat).addClass("catunselected");
    } else {
        toggler.addClass("catselected");
        addCategory(cat);
        $(".cat-" + cat).removeClass("catunselected");
    }
}

$(document).ready(function () {

    setCategoryLinks();

    $('#timetoggle').click(
        function (evt) {
            evt.preventDefault();
            toggle_time();
            return false;
        });
    $('.category_toggle').click(
        function (evt) {
            evt.preventDefault();
            toggleCategory(this.id);
        });
});

$(document).ready(function() {

  var start = moment();
  var end = moment().add(6, 'days');
  var beginningoftime = '01/01/2020';
  var endoftime = '01/01/2050';



  $('input[name="daterange"]').on('cancel.daterangepicker', function(ev, picker) {
      $(this).val('');
  });

    $('#daterange').daterangepicker({
        startDate: start,
        endDate: end,
        autoUpdateInput: false,
        opens: "center",
        drops: "down",
        ranges: {
           'No restriction': [beginningoftime, endoftime],
           'Future': [moment(), endoftime],
           'Past': [beginningoftime, moment()],
           'Today': [moment(), moment()],
           'Next 7 Days': [moment(), moment().add(6, 'days')],
           'Next 30 Days': [moment(), moment().add(29, 'days')],
        },
      },
      function(start, end, label) {
      if(start.format('MM/DD/YYYY') == beginningoftime){
        start = '';
      } else {
        start = start.format('MMMM D, YYYY')
      }
      if(end.format('MM/DD/YYYY') == endoftime) {
        end = '';
      } else {
        end =  end.format('MMMM D, YYYY')
      }
      // everything is a string from now on
      if(start == "Invalid date") {
        start = ''
      }
      if(end == "Invalid date") {
        end = ''
      }
      if(start == '' && end == '') {
        $('#daterange').val('');
      } else {
        $('#daterange').val(start + ' - ' + end);
      }
    }
    );

    //cb(start, end);


});



