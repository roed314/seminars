
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
const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
document.cookie = "browser_timezone=" + tz + ";path=/"

$(document).ready(function () {

    $('#timetoggle').click(
        function (evt) {
            evt.preventDefault();
            toggle_time();
            return false;
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



