/* ==========================================================================
   Time Tracker — frontend (jQuery)
   Talks to the FastAPI backend under /api.
   ========================================================================== */
(function ($) {
  'use strict';

  var API = '/api';
  var state = {
    tz: '',
    allowOverlap: false,
    maxNoteLength: 2000,
    editingId: null,
    deletingId: null
  };

  /* ---------------------------------------------------------------- utils */

  function pad(n) { return n < 10 ? '0' + n : String(n); }

  /** Date -> value for <input type="datetime-local"> (browser-local parts). */
  function toInputValue(d) {
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) +
      'T' + pad(d.getHours()) + ':' + pad(d.getMinutes());
  }

  /** ISO string from the API (with UTC offset) -> Date. */
  function parseIso(iso) { return new Date(iso); }

  function hhmm(date) {
    return pad(date.getHours()) + ':' + pad(date.getMinutes());
  }

  function prettyDateTime(date) {
    return date.toLocaleDateString(undefined, { day: '2-digit', month: 'short' }) + ' ' + hhmm(date);
  }

  function dayTitle(isoDay, weekday) {
    var parts = isoDay.split('-').map(Number);
    var d = new Date(parts[0], parts[1] - 1, parts[2]);
    var today = new Date(); today.setHours(0, 0, 0, 0);
    var diff = Math.round((d - today) / 86400000);
    var rel = '';
    if (diff === 0) rel = ' · Today';
    else if (diff === -1) rel = ' · Yesterday';
    else if (diff === 1) rel = ' · Tomorrow';

    return weekday + ', ' + d.toLocaleDateString(undefined, {
      day: 'numeric', month: 'long', year: 'numeric'
    }) + rel;
  }

  function humanDuration(seconds) {
    var total = Math.round(Math.abs(seconds));
    var sign = seconds < 0 ? '-' : '';
    var h = Math.floor(total / 3600);
    var m = Math.floor((total % 3600) / 60);
    var s = total % 60;
    if (h) return sign + h + 'h ' + pad(m) + 'm';
    if (m) return sign + m + 'm ' + pad(s) + 's';
    return sign + s + 's';
  }

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  /** Naive pluraliser, with the handful of irregulars this UI uses. */
  function plural(n, word) {
    if (n === 1) return n + ' ' + word;
    var irregular = { entry: 'entries', day: 'days', hour: 'hours' };
    return n + ' ' + (irregular[word] || word + 's');
  }

  /** FastAPI returns {detail: "..."} or {detail: [{...}]}; flatten to text. */
  function errorText(xhr) {
    var data = xhr && xhr.responseJSON;
    if (!data) return (xhr && xhr.statusText) || 'Request failed';
    var d = data.detail;
    if (typeof d === 'string') return d;
    if ($.isArray(d)) {
      return d.map(function (e) { return e.msg || JSON.stringify(e); }).join('; ');
    }
    return 'HTTP ' + (xhr.status || '?');
  }

  /* --------------------------------------------------------------- toasts */

  function toast(message, kind) {
    var palette = {
      success: 'bg-emerald-600',
      error: 'bg-red-600',
      info: 'bg-slate-800'
    };
    var $t = $('<div>')
      .addClass('pointer-events-auto w-full rounded-lg px-4 py-2.5 text-sm font-medium text-white shadow-lg transition-opacity duration-300')
      .addClass(palette[kind] || palette.info)
      .text(message);
    $('#toasts').append($t);
    setTimeout(function () {
      $t.css('opacity', 0);
      setTimeout(function () { $t.remove(); }, 320);
    }, kind === 'error' ? 5200 : 2600);
  }

  /* ---------------------------------------------------------------- states */

  function showState(which, msg) {
    $('#stateLoading, #stateEmpty, #stateError').addClass('hidden');
    if (which === 'loading') $('#stateLoading').removeClass('hidden');
    if (which === 'empty') $('#stateEmpty').removeClass('hidden');
    if (which === 'error') {
      $('#stateErrorMsg').text(msg || 'Unknown error');
      $('#stateError').removeClass('hidden');
    }
  }

  /* -------------------------------------------------------------- rendering */

  function renderDays(payload) {
    var $wrap = $('#days').empty();

    $('#rangeTotal').text(payload.entry_count
      ? humanDuration(payload.total_seconds) + ' tracked in this view'
      : '');
    $('#rangeCount').text(payload.entry_count
      ? plural(payload.entry_count, 'entry') + ' · ' + plural(payload.days.length, 'day')
      : '');

    if (!payload.entry_count) {
      showState('empty');
      return;
    }
    showState(null);

    var dayTpl = $('#tplDay').html();
    var rowTpl = $('#tplEntry').html();

    $.each(payload.days, function (_, day) {
      var $day = $(dayTpl);
      $day.find('[data-f="title"]').text(dayTitle(day.day, day.weekday));
      $day.find('[data-f="count"]').text(plural(day.entry_count, 'entry'));
      $day.find('[data-f="total"]').text(day.total_human);

      var $list = $day.find('[data-f="list"]');

      $.each(day.entries, function (_, entry) {
        var $row = $(rowTpl);
        var start = parseIso(entry.start_at);
        var end = parseIso(entry.end_at);
        var crossesDay = start.toDateString() !== end.toDateString();

        $row.attr('data-id', entry.id);
        $row.find('[data-f="start"]').text(hhmm(start));
        $row.find('[data-f="end"]').text(crossesDay ? prettyDateTime(end) : hhmm(end));
        $row.find('[data-f="duration"]').text(entry.duration_human);

        var note = entry.note && entry.note.length
          ? entry.note
          : '<span class="italic text-slate-400">No note</span>';
        $row.find('[data-f="note"]').html(
          entry.note && entry.note.length ? escapeHtml(entry.note) : note
        );

        $row.find('[data-f="range"]').text(
          prettyDateTime(start) + ' → ' + prettyDateTime(end)
        );
        $row.find('[data-f="range"]').attr('title', entry.duration_human);

        $list.append($row);
      });

      $wrap.append($day);
    });
  }

  /* -------------------------------------------------------------- API layer */

  function currentFilters() {
    var f = {};
    var s = $('#filterStart').val();
    var e = $('#filterEnd').val();
    var q = $.trim($('#filterQ').val());
    if (s) f.start = s;
    if (e) f.end = e;
    if (q) f.q = q;
    return f;
  }

  function loadDays() {
    showState('loading');
    $('#days').empty();

    var filters = currentFilters();
    var query = $.param(filters);

    return $.ajax({
      url: API + '/entries/days' + (query ? '?' + query : ''),
      method: 'GET',
      dataType: 'json'
    }).done(function (payload) {
      renderDays(payload);
    }).fail(function (xhr) {
      $('#days').empty();
      $('#rangeTotal').text('');
      $('#rangeCount').text('');
      showState('error', errorText(xhr));
    });
  }

  function loadSummary() {
    return $.getJSON(API + '/entries/summary')
      .done(function (s) {
        $('#statToday').text(s.today_human);
        $('#statTodayCount').text(plural(s.today_count, 'entry'));
        $('#statWeek').text(s.week_human);
        $('#statWeekCount').text(plural(s.week_count, 'entry'));
        $('#statAll').text(s.all_time_human);
        $('#statAllCount').text(plural(s.all_time_count, 'entry'));
      })
      .fail(function () {
        $('#statToday, #statWeek, #statAll').text('—');
      });
  }

  function refreshAll() {
    return $.when(loadDays(), loadSummary());
  }

  function loadConfig() {
    return $.getJSON(API + '/config').done(function (cfg) {
      state.tz = cfg.timezone;
      state.allowOverlap = !!cfg.allow_overlap;
      state.maxNoteLength = cfg.max_note_length || 2000;

      $('#tzLabel').text('Times shown in ' + cfg.timezone);
      $('#modalTz').text(cfg.timezone);
      $('#fNote').attr('maxlength', state.maxNoteLength);

      if (state.allowOverlap) {
        $('#overlapNote').text(' · overlaps allowed').removeClass('hidden');
      } else {
        $('#overlapNote').text(' · overlap check on').removeClass('hidden');
      }
    });
  }

  /* ----------------------------------------------------------------- modal */

  function showFormError(msg) {
    if (!msg) { $('#formError').addClass('hidden').text(''); return; }
    $('#formError').removeClass('hidden').text(msg);
  }

  function updatePreview() {
    var s = $('#fStart').val();
    var e = $('#fEnd').val();
    if (!s || !e) { $('#previewDuration').text('—'); return; }
    var diff = (new Date(e) - new Date(s)) / 1000;
    if (isNaN(diff)) { $('#previewDuration').text('—'); return; }
    $('#previewDuration').text(diff > 0 ? humanDuration(diff) : 'invalid');
  }

  function openModal(entry) {
    showFormError('');
    $('#entryForm')[0].reset();
    $('#noteCount').text('0');

    if (entry) {
      state.editingId = entry.id;
      $('#modalTitle').text('Edit time entry #' + entry.id);
      $('#btnSave').text('Save changes');
      $('#fStart').val(toInputValue(parseIso(entry.start_at)));
      $('#fEnd').val(toInputValue(parseIso(entry.end_at)));
      $('#fNote').val(entry.note || '');
    } else {
      state.editingId = null;
      $('#modalTitle').text('New time entry');
      $('#btnSave').text('Save entry');
      var now = new Date();
      var start = new Date(now.getTime() - 60 * 60 * 1000);
      start.setSeconds(0, 0);
      now.setSeconds(0, 0);
      $('#fStart').val(toInputValue(start));
      $('#fEnd').val(toInputValue(now));
    }

    $('#noteCount').text(($('#fNote').val() || '').length);
    updatePreview();
    $('#modal').removeClass('hidden');
    setTimeout(function () { $('#fStart').trigger('focus'); }, 30);
  }

  function closeModal() {
    $('#modal').addClass('hidden');
    state.editingId = null;
  }

  function submitForm(ev) {
    ev.preventDefault();
    showFormError('');

    var startVal = $('#fStart').val();
    var endVal = $('#fEnd').val();

    if (!startVal || !endVal) {
      showFormError('Both start and end date-time are required.');
      return;
    }

    var start = new Date(startVal);
    var end = new Date(endVal);

    if (isNaN(start.getTime()) || isNaN(end.getTime())) {
      showFormError('Could not parse the supplied date-times.');
      return;
    }
    if (end <= start) {
      showFormError('End must be after start.');
      return;
    }

    var payload = {
      start_at: start.toISOString(),
      end_at: end.toISOString(),
      note: $('#fNote').val() || ''
    };

    var isEdit = state.editingId !== null;
    var $btn = $('#btnSave').prop('disabled', true).text(isEdit ? 'Updating…' : 'Saving…');

    $.ajax({
      url: API + '/entries' + (isEdit ? '/' + state.editingId : ''),
      method: isEdit ? 'PATCH' : 'POST',
      contentType: 'application/json',
      data: JSON.stringify(payload),
      dataType: 'json'
    }).done(function (saved) {
      closeModal();
      toast(isEdit ? 'Entry updated (' + saved.duration_human + ')'
                   : 'Logged ' + saved.duration_human, 'success');
      refreshAll();
    }).fail(function (xhr) {
      showFormError(errorText(xhr));
    }).always(function () {
      $btn.prop('disabled', false).text(isEdit ? 'Save changes' : 'Save entry');
    });
  }

  /* ---------------------------------------------------------------- delete */

  function askDelete(entry) {
    state.deletingId = entry.id;
    var start = parseIso(entry.start_at);
    $('#confirmText').text(
      entry.duration_human + ' — ' + prettyDateTime(start) +
      (entry.note ? ' · ' + entry.note : '') + '. This cannot be undone.'
    );
    $('#confirmModal').removeClass('hidden');
  }

  function closeConfirm() {
    $('#confirmModal').addClass('hidden');
    state.deletingId = null;
  }

  function doDelete() {
    if (state.deletingId === null) return;
    var id = state.deletingId;
    $('#btnConfirmDelete').prop('disabled', true).text('Deleting…');

    $.ajax({ url: API + '/entries/' + id, method: 'DELETE' })
      .done(function () {
        closeConfirm();
        toast('Entry deleted', 'success');
        refreshAll();
      })
      .fail(function (xhr) {
        toast(errorText(xhr), 'error');
      })
      .always(function () {
        $('#btnConfirmDelete').prop('disabled', false).text('Delete');
      });
  }

  /* ----------------------------------------------------------------- quicks */

  function applyQuick(kind) {
    var now = new Date();
    now.setSeconds(0, 0);

    if (kind === 'last-hour') {
      var from = new Date(now.getTime() - 3600000);
      $('#fStart').val(toInputValue(from));
      $('#fEnd').val(toInputValue(now));
    } else if (kind === 'since-9') {
      var nine = new Date(now);
      nine.setHours(9, 0, 0, 0);
      if (nine > now) nine.setDate(nine.getDate() - 1);
      $('#fStart').val(toInputValue(nine));
      $('#fEnd').val(toInputValue(now));
    } else if (kind === 'now-end') {
      $('#fEnd').val(toInputValue(now));
    }
    updatePreview();
  }

  /* ------------------------------------------------------------------ init */

  $(function () {
    loadConfig().always(refreshAll);

    $('#btnNew, #btnNewEmpty').on('click', function () { openModal(null); });
    $('#btnRefresh').on('click', function () {
      refreshAll().always(function () { toast('Reloaded', 'info'); });
    });

    $('#btnFilter').on('click', loadDays);
    $('#btnFilterClear').on('click', function () {
      $('#filterStart, #filterEnd, #filterQ').val('');
      loadDays();
    });
    $('#filterQ').on('keydown', function (e) { if (e.key === 'Enter') loadDays(); });
    $('#filterStart, #filterEnd').on('change', loadDays);

    // modal
    $('#modal').on('click', '[data-close]', closeModal);
    $('#confirmModal').on('click', '[data-close-confirm]', closeConfirm);
    $('#entryForm').on('submit', submitForm);
    $('#fStart, #fEnd').on('change input', updatePreview);
    $('#fNote').on('input', function () { $('#noteCount').text(this.value.length); });
    $('#modal').on('click', '[data-quick]', function () { applyQuick($(this).data('quick')); });
    $('#btnConfirmDelete').on('click', doDelete);

    // row actions (delegated)
    $('#days').on('click', '[data-act="edit"]', function () {
      var id = $(this).closest('li').data('id');
      $.getJSON(API + '/entries/' + id)
        .done(function (entry) { openModal(entry); })
        .fail(function (xhr) { toast(errorText(xhr), 'error'); });
    });
    $('#days').on('click', '[data-act="delete"]', function () {
      var $row = $(this).closest('li');
      var id = $row.data('id');
      $.getJSON(API + '/entries/' + id)
        .done(function (entry) { askDelete(entry); })
        .fail(function (xhr) { toast(errorText(xhr), 'error'); });
    });

    // Escape closes topmost overlay; Ctrl/Cmd+Enter saves
    $(document).on('keydown', function (e) {
      if (e.key === 'Escape') {
        if (!$('#confirmModal').hasClass('hidden')) closeConfirm();
        else if (!$('#modal').hasClass('hidden')) closeModal();
      }
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && !$('#modal').hasClass('hidden')) {
        $('#entryForm').trigger('submit');
      }
    });
  });
})(jQuery);
