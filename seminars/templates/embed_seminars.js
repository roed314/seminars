// Keep public namespace clean
(function(root) {

  // constructor
  function SeminarEmbedder() {
    // anything to do?
  };

  // Prototype for class controlling the embedding
  SeminarEmbedder.prototype = {
    initialized: false,

  };

  //////////////////////////////

  SeminarEmbedder.prototype.processEmbeds = function() {
    var targets = document.getElementsByClassName('embeddable_schedule');
    var copyTargets = []; // The return value above is mutable.... changes under our feet
    for (var i=0; i < targets.length; ++i) {
      copyTargets[i] = targets[i];
    };
    for (var i=0; i < copyTargets.length; ++i) {
      this.startEmbed(copyTargets[i]);
    };
  };

  SeminarEmbedder.prototype.startEmbed = function(target) {
    var shortname = target.getAttribute('shortname');

    if (!shortname)
      return;

    var fetchURL  = "{{ url_for('show_seminar_bare', shortname='_SHORTNAME_', _external=True, _scheme=scheme) }}".replace('_SHORTNAME_', shortname) ;

    var daterange = target.getAttribute('daterange');

    if (daterange) {
      if ("future" == daterange.toLowerCase()) {
        fetchURL += "?future=";
      } else if ("past" == daterange.toLowerCase()) {
        fetchURL += "?past=";
      } else {
        fetchURL += "?daterange=" + encodeURI(daterange);
      }
    }

    var xhr = new XMLHttpRequest();
    xhr.responseType = "document";

    self = this;
    xhr.addEventListener("load", function(event) { response = this.responseXML; self.finishEmbed(target, event, response); });
    xhr.addEventListener("error", function(event) { self.transferFailed(target, event); });
    xhr.addEventListener("abort", function(event) { self.transferCanceled(target, event); });
    xhr.addEventListener("progress", function(event) { self.updateProgress(target, event); });

    console.log("Initiating fetch from " + fetchURL);
    xhr.open("GET", fetchURL, true);

    // Mark it as processing by changing the class
    target.classList.remove("embeddable_schedule");
    target.classList.add("embedding_in_prog_schedule");

    xhr.send();

  }

  SeminarEmbedder.prototype.finishEmbed = function(target, event, response) {

    target.innerText = "";
    target.appendChild(response.getElementById('embed_content'));

    // Mark it as processed by changing the class
    target.classList.remove("embedding_in_prog_schedule");
    target.classList.add("embedded_schedule");
  }

  SeminarEmbedder.prototype.updateProgress = function(target, event) {
    target.innerText += ".";
  }

  SeminarEmbedder.prototype.transferCanceled = function(target, event) {
    target.innerText = "Transfer cancelled for embedding!";

    // Mark it as failed by changing the class
    target.classList.remove("embedding_in_prog_schedule");
    target.classList.add("embedding_failed_schedule");
  }

  SeminarEmbedder.prototype.transferFailed = function(target, event) {
    target.innerText = "Transfer failed for embedding!";

    // Mark it as failed by changing the class
    target.classList.remove("embedding_in_prog_schedule");
    target.classList.add("embedding_failed_schedule");
  }

  //////////////////////////////

  var seminarEmbedder = new SeminarEmbedder();

  root['seminarEmbedder'] = seminarEmbedder;

  document.addEventListener('DOMContentLoaded', (event) => {
    seminarEmbedder.initialized = true;
    seminarEmbedder.processEmbeds();
  });

})(this);
