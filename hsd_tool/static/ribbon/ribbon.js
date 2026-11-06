// \0rolldown/runtime.js
var e = (e, t) => () => (t || (e((t = { exports: {} }).exports, t, t.exports), e = null), t.exports), t = /* @__PURE__ */ e(((e) => {
	function t(e, t) {
		var n = e.length;
		e.push(t);
		a: for (; 0 < n;) {
			var r = n - 1 >>> 1, a = e[r];
			if (0 < i(a, t)) e[r] = t, e[n] = a, n = r;
			else break a;
		}
	}
	function n(e) {
		return e.length === 0 ? null : e[0];
	}
	function r(e) {
		if (e.length === 0) return null;
		var t = e[0], n = e.pop();
		if (n !== t) {
			e[0] = n;
			a: for (var r = 0, a = e.length, o = a >>> 1; r < o;) {
				var s = 2 * (r + 1) - 1, c = e[s], l = s + 1, u = e[l];
				if (0 > i(c, n)) l < a && 0 > i(u, c) ? (e[r] = u, e[l] = n, r = l) : (e[r] = c, e[s] = n, r = s);
				else if (l < a && 0 > i(u, n)) e[r] = u, e[l] = n, r = l;
				else break a;
			}
		}
		return t;
	}
	function i(e, t) {
		var n = e.sortIndex - t.sortIndex;
		return n === 0 ? e.id - t.id : n;
	}
	if (e.unstable_now = void 0, typeof performance == "object" && typeof performance.now == "function") {
		var a = performance;
		e.unstable_now = function() {
			return a.now();
		};
	} else {
		var o = Date, s = o.now();
		e.unstable_now = function() {
			return o.now() - s;
		};
	}
	var c = [], l = [], u = 1, d = null, f = 3, p = !1, m = !1, h = !1, g = !1, _ = typeof setTimeout == "function" ? setTimeout : null, v = typeof clearTimeout == "function" ? clearTimeout : null, y = typeof setImmediate < "u" ? setImmediate : null;
	function b(e) {
		for (var i = n(l); i !== null;) {
			if (i.callback === null) r(l);
			else if (i.startTime <= e) r(l), i.sortIndex = i.expirationTime, t(c, i);
			else break;
			i = n(l);
		}
	}
	function ee(e) {
		if (h = !1, b(e), !m) {
			if (n(c) !== null) m = !0, x || (x = !0, re());
			else {
				var t = n(l);
				t !== null && D(ee, t.startTime - e);
			}
		}
	}
	var x = !1, S = -1, te = 5, C = -1;
	function ne() {
		return g ? !0 : !(e.unstable_now() - C < te);
	}
	function w() {
		if (g = !1, x) {
			var t = e.unstable_now();
			C = t;
			var i = !0;
			try {
				a: {
					m = !1, h && (h = !1, v(S), S = -1), p = !0;
					var a = f;
					try {
						b: {
							for (b(t), d = n(c); d !== null && !(d.expirationTime > t && ne());) {
								var o = d.callback;
								if (typeof o == "function") {
									d.callback = null, f = d.priorityLevel;
									var s = o(d.expirationTime <= t);
									if (t = e.unstable_now(), typeof s == "function") {
										d.callback = s, b(t), i = !0;
										break b;
									}
									d === n(c) && r(c), b(t);
								} else r(c);
								d = n(c);
							}
							if (d !== null) i = !0;
							else {
								var u = n(l);
								u !== null && D(ee, u.startTime - t), i = !1;
							}
						}
						break a;
					} finally {
						d = null, f = a, p = !1;
					}
					i = void 0;
				}
			} finally {
				i ? re() : x = !1;
			}
		}
	}
	var re;
	if (typeof y == "function") re = function() {
		y(w);
	};
	else if (typeof MessageChannel < "u") {
		var T = new MessageChannel(), E = T.port2;
		T.port1.onmessage = w, re = function() {
			E.postMessage(null);
		};
	} else re = function() {
		_(w, 0);
	};
	function D(t, n) {
		S = _(function() {
			t(e.unstable_now());
		}, n);
	}
	e.unstable_IdlePriority = 5, e.unstable_ImmediatePriority = 1, e.unstable_LowPriority = 4, e.unstable_NormalPriority = 3, e.unstable_Profiling = null, e.unstable_UserBlockingPriority = 2, e.unstable_cancelCallback = function(e) {
		e.callback = null;
	}, e.unstable_forceFrameRate = function(e) {
		0 > e || 125 < e ? console.error("forceFrameRate takes a positive int between 0 and 125, forcing frame rates higher than 125 fps is not supported") : te = 0 < e ? Math.floor(1e3 / e) : 5;
	}, e.unstable_getCurrentPriorityLevel = function() {
		return f;
	}, e.unstable_next = function(e) {
		switch (f) {
			case 1:
			case 2:
			case 3:
				var t = 3;
				break;
			default: t = f;
		}
		var n = f;
		f = t;
		try {
			return e();
		} finally {
			f = n;
		}
	}, e.unstable_requestPaint = function() {
		g = !0;
	}, e.unstable_runWithPriority = function(e, t) {
		switch (e) {
			case 1:
			case 2:
			case 3:
			case 4:
			case 5: break;
			default: e = 3;
		}
		var n = f;
		f = e;
		try {
			return t();
		} finally {
			f = n;
		}
	}, e.unstable_scheduleCallback = function(r, i, a) {
		var o = e.unstable_now();
		switch (typeof a == "object" && a ? (a = a.delay, a = typeof a == "number" && 0 < a ? o + a : o) : a = o, r) {
			case 1:
				var s = -1;
				break;
			case 2:
				s = 250;
				break;
			case 5:
				s = 1073741823;
				break;
			case 4:
				s = 1e4;
				break;
			default: s = 5e3;
		}
		return s = a + s, r = {
			id: u++,
			callback: i,
			priorityLevel: r,
			startTime: a,
			expirationTime: s,
			sortIndex: -1
		}, a > o ? (r.sortIndex = a, t(l, r), n(c) === null && r === n(l) && (h ? (v(S), S = -1) : h = !0, D(ee, a - o))) : (r.sortIndex = s, t(c, r), m || p || (m = !0, x || (x = !0, re()))), r;
	}, e.unstable_shouldYield = ne, e.unstable_wrapCallback = function(e) {
		var t = f;
		return function() {
			var n = f;
			f = t;
			try {
				return e.apply(this, arguments);
			} finally {
				f = n;
			}
		};
	};
})), n = /* @__PURE__ */ e(((e, n) => {
	n.exports = t();
})), r = /* @__PURE__ */ e(((e) => {
	var t = Symbol.for("react.transitional.element"), n = Symbol.for("react.portal"), r = Symbol.for("react.fragment"), i = Symbol.for("react.strict_mode"), a = Symbol.for("react.profiler"), o = Symbol.for("react.consumer"), s = Symbol.for("react.context"), c = Symbol.for("react.forward_ref"), l = Symbol.for("react.suspense"), u = Symbol.for("react.memo"), d = Symbol.for("react.lazy"), f = Symbol.for("react.activity"), p = Symbol.for("react.view_transition"), m = Symbol.iterator;
	function h(e) {
		return typeof e != "object" || !e ? null : (e = m && e[m] || e["@@iterator"], typeof e == "function" ? e : null);
	}
	var g = {
		isMounted: function() {
			return !1;
		},
		enqueueForceUpdate: function() {},
		enqueueReplaceState: function() {},
		enqueueSetState: function() {}
	}, _ = Object.assign, v = {};
	function y(e, t, n) {
		this.props = e, this.context = t, this.refs = v, this.updater = n || g;
	}
	y.prototype.isReactComponent = {}, y.prototype.setState = function(e, t) {
		if (typeof e != "object" && typeof e != "function" && e != null) throw Error("takes an object of state variables to update or a function which returns an object of state variables.");
		this.updater.enqueueSetState(this, e, t, "setState");
	}, y.prototype.forceUpdate = function(e) {
		this.updater.enqueueForceUpdate(this, e, "forceUpdate");
	};
	function b() {}
	b.prototype = y.prototype;
	function ee(e, t, n) {
		this.props = e, this.context = t, this.refs = v, this.updater = n || g;
	}
	var x = ee.prototype = new b();
	x.constructor = ee, _(x, y.prototype), x.isPureReactComponent = !0;
	var S = Array.isArray;
	function te() {}
	var C = {
		H: null,
		A: null,
		T: null,
		S: null
	}, ne = Object.prototype.hasOwnProperty;
	function w(e, n, r) {
		var i = r.ref;
		return {
			$$typeof: t,
			type: e,
			key: n,
			ref: i === void 0 ? null : i,
			props: r
		};
	}
	function re(e, t) {
		return w(e.type, t, e.props);
	}
	function T(e) {
		return typeof e == "object" && !!e && e.$$typeof === t;
	}
	function E(e) {
		var t = {
			"=": "=0",
			":": "=2"
		};
		return "$" + e.replace(/[=:]/g, function(e) {
			return t[e];
		});
	}
	var D = /\/+/g;
	function ie(e, t) {
		return typeof e == "object" && e && e.key != null ? E("" + e.key) : t.toString(36);
	}
	function ae(e) {
		switch (e.status) {
			case "fulfilled": return e.value;
			case "rejected": throw e.reason;
			default: switch (typeof e.status == "string" ? e.then(te, te) : (e.status = "pending", e.then(function(t) {
				e.status === "pending" && (e.status = "fulfilled", e.value = t);
			}, function(t) {
				e.status === "pending" && (e.status = "rejected", e.reason = t);
			})), e.status) {
				case "fulfilled": return e.value;
				case "rejected": throw e.reason;
			}
		}
		throw e;
	}
	function oe(e, r, i, a, o) {
		var s = typeof e;
		(s === "undefined" || s === "boolean") && (e = null);
		var c = !1;
		if (e === null) c = !0;
		else switch (s) {
			case "bigint":
			case "string":
			case "number":
				c = !0;
				break;
			case "object": switch (e.$$typeof) {
				case t:
				case n:
					c = !0;
					break;
				case d: return c = e._init, oe(c(e._payload), r, i, a, o);
			}
		}
		if (c) return o = o(e), c = a === "" ? "." + ie(e, 0) : a, S(o) ? (i = "", c != null && (i = c.replace(D, "$&/") + "/"), oe(o, r, i, "", function(e) {
			return e;
		})) : o != null && (T(o) && (o = re(o, i + (o.key == null || e && e.key === o.key ? "" : ("" + o.key).replace(D, "$&/") + "/") + c)), r.push(o)), 1;
		c = 0;
		var l = a === "" ? "." : a + ":";
		if (S(e)) for (var u = 0; u < e.length; u++) a = e[u], s = l + ie(a, u), c += oe(a, r, i, s, o);
		else if (u = h(e), typeof u == "function") for (e = u.call(e), u = 0; !(a = e.next()).done;) a = a.value, s = l + ie(a, u++), c += oe(a, r, i, s, o);
		else if (s === "object") {
			if (typeof e.then == "function") return oe(ae(e), r, i, a, o);
			throw r = String(e), Error("Objects are not valid as a React child (found: " + (r === "[object Object]" ? "object with keys {" + Object.keys(e).join(", ") + "}" : r) + "). If you meant to render a collection of children, use an array instead.");
		}
		return c;
	}
	function se(e, t, n) {
		if (e == null) return e;
		var r = [], i = 0;
		return oe(e, r, "", "", function(e) {
			return t.call(n, e, i++);
		}), r;
	}
	function ce(e) {
		if (e._status === -1) {
			var t = e._result, n = t();
			n.then(function(t) {
				(e._status === 0 || e._status === -1) && (e._status = 1, e._result = t, n.status === void 0 && (n.status = "fulfilled", n.value = t));
			}, function(t) {
				(e._status === 0 || e._status === -1) && (e._status = 2, e._result = t, n.status === void 0 && (n.status = "rejected", n.reason = t));
			}), e._status === -1 && (e._status = 0, e._result = n);
		}
		if (e._status === 1) return e._result.default;
		throw e._result;
	}
	var O = typeof reportError == "function" ? reportError : function(e) {
		if (typeof window == "object" && typeof window.ErrorEvent == "function") {
			var t = new window.ErrorEvent("error", {
				bubbles: !0,
				cancelable: !0,
				message: typeof e == "object" && e && typeof e.message == "string" ? String(e.message) : String(e),
				error: e
			});
			if (!window.dispatchEvent(t)) return;
		} else if (typeof process == "object" && typeof process.emit == "function") {
			process.emit("uncaughtException", e);
			return;
		}
		console.error(e);
	};
	function le(e) {
		var t = C.T, n = {};
		n.types = t === null ? null : t.types, C.T = n;
		try {
			var r = e(), i = C.S;
			i !== null && i(n, r), typeof r == "object" && r && typeof r.then == "function" && r.then(te, O);
		} catch (e) {
			O(e);
		} finally {
			t !== null && n.types !== null && (t.types = n.types), C.T = t;
		}
	}
	function ue(e) {
		var t = C.T;
		if (t !== null) {
			var n = t.types;
			n === null ? t.types = [e] : n.indexOf(e) === -1 && n.push(e);
		} else le(ue.bind(null, e));
	}
	var de = {
		map: se,
		forEach: function(e, t, n) {
			se(e, function() {
				t.apply(this, arguments);
			}, n);
		},
		count: function(e) {
			var t = 0;
			return se(e, function() {
				t++;
			}), t;
		},
		toArray: function(e) {
			return se(e, function(e) {
				return e;
			}) || [];
		},
		only: function(e) {
			if (!T(e)) throw Error("React.Children.only expected to receive a single React element child.");
			return e;
		}
	};
	e.Activity = f, e.Children = de, e.Component = y, e.Fragment = r, e.Profiler = a, e.PureComponent = ee, e.StrictMode = i, e.Suspense = l, e.ViewTransition = p, e.__CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE = C, e.__COMPILER_RUNTIME = {
		__proto__: null,
		c: function(e) {
			return C.H.useMemoCache(e);
		}
	}, e.addTransitionType = ue, e.cache = function(e) {
		return function() {
			return e.apply(null, arguments);
		};
	}, e.cacheSignal = function() {
		return null;
	}, e.cloneElement = function(e, t, n) {
		if (e == null) throw Error("The argument must be a React element, but you passed " + e + ".");
		var r = _({}, e.props), i = e.key;
		if (t != null) for (a in t.key !== void 0 && (i = "" + t.key), t) !ne.call(t, a) || a === "key" || a === "__self" || a === "__source" || a === "ref" && t.ref === void 0 || (r[a] = t[a]);
		var a = arguments.length - 2;
		if (a === 1) r.children = n;
		else if (1 < a) {
			for (var o = Array(a), s = 0; s < a; s++) o[s] = arguments[s + 2];
			r.children = o;
		}
		return w(e.type, i, r);
	}, e.createContext = function(e) {
		return e = {
			$$typeof: s,
			_currentValue: e,
			_currentValue2: e,
			_threadCount: 0,
			Provider: null,
			Consumer: null
		}, e.Provider = e, e.Consumer = {
			$$typeof: o,
			_context: e
		}, e;
	}, e.createElement = function(e, t, n) {
		var r, i = {}, a = null;
		if (t != null) for (r in t.key !== void 0 && (a = "" + t.key), t) ne.call(t, r) && r !== "key" && r !== "__self" && r !== "__source" && (i[r] = t[r]);
		var o = arguments.length - 2;
		if (o === 1) i.children = n;
		else if (1 < o) {
			for (var s = Array(o), c = 0; c < o; c++) s[c] = arguments[c + 2];
			i.children = s;
		}
		if (e && e.defaultProps) for (r in o = e.defaultProps, o) i[r] === void 0 && (i[r] = o[r]);
		return w(e, a, i);
	}, e.createRef = function() {
		return { current: null };
	}, e.forwardRef = function(e) {
		return {
			$$typeof: c,
			render: e
		};
	}, e.isValidElement = T, e.lazy = function(e) {
		return {
			$$typeof: d,
			_payload: {
				_status: -1,
				_result: e
			},
			_init: ce
		};
	}, e.memo = function(e, t) {
		return {
			$$typeof: u,
			type: e,
			compare: t === void 0 ? null : t
		};
	}, e.startTransition = le, e.unstable_useCacheRefresh = function() {
		return C.H.useCacheRefresh();
	}, e.use = function(e) {
		return C.H.use(e);
	}, e.useActionState = function(e, t, n) {
		return C.H.useActionState(e, t, n);
	}, e.useCallback = function(e, t) {
		return C.H.useCallback(e, t);
	}, e.useContext = function(e) {
		return C.H.useContext(e);
	}, e.useDebugValue = function() {}, e.useDeferredValue = function(e, t) {
		return C.H.useDeferredValue(e, t);
	}, e.useEffect = function(e, t) {
		return C.H.useEffect(e, t);
	}, e.useEffectEvent = function(e) {
		return C.H.useEffectEvent(e);
	}, e.useId = function() {
		return C.H.useId();
	}, e.useImperativeHandle = function(e, t, n) {
		return C.H.useImperativeHandle(e, t, n);
	}, e.useInsertionEffect = function(e, t) {
		return C.H.useInsertionEffect(e, t);
	}, e.useLayoutEffect = function(e, t) {
		return C.H.useLayoutEffect(e, t);
	}, e.useMemo = function(e, t) {
		return C.H.useMemo(e, t);
	}, e.useOptimistic = function(e, t) {
		return C.H.useOptimistic(e, t);
	}, e.useReducer = function(e, t, n) {
		return C.H.useReducer(e, t, n);
	}, e.useRef = function(e) {
		return C.H.useRef(e);
	}, e.useState = function(e) {
		return C.H.useState(e);
	}, e.useSyncExternalStore = function(e, t, n) {
		return C.H.useSyncExternalStore(e, t, n);
	}, e.useTransition = function() {
		return C.H.useTransition();
	}, e.version = "19.3.1";
})), i = /* @__PURE__ */ e(((e, t) => {
	t.exports = r();
})), a = /* @__PURE__ */ e(((e) => {
	var t = i();
	function n(e) {
		var t = "https://react.dev/errors/" + e;
		if (1 < arguments.length) {
			t += "?args[]=" + encodeURIComponent(arguments[1]);
			for (var n = 2; n < arguments.length; n++) t += "&args[]=" + encodeURIComponent(arguments[n]);
		}
		return "Minified React error #" + e + "; visit " + t + " for the full message or use the non-minified dev environment for full errors and additional helpful warnings.";
	}
	function r() {}
	var a = {
		d: {
			f: r,
			r: function() {
				throw Error(n(522));
			},
			D: r,
			C: r,
			L: r,
			m: r,
			X: r,
			S: r,
			M: r
		},
		p: 0,
		findDOMNode: null
	}, o = Symbol.for("react.portal"), s = Symbol.for("react.recoverable"), c = Symbol.for("react.optimistic_key");
	function l(e, t, n) {
		var r = 3 < arguments.length && arguments[3] !== void 0 ? arguments[3] : null;
		return {
			$$typeof: o,
			key: r == null ? null : r === c ? c : "" + r,
			children: e,
			containerInfo: t,
			implementation: n
		};
	}
	var u = t.__CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE;
	function d(e, t) {
		if (e === "font") return "";
		if (typeof t == "string") return t === "use-credentials" ? t : "";
	}
	e.__DOM_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE = a, e.browser = function(e) {
		return {
			$$typeof: s,
			_reason: e
		};
	}, e.createPortal = function(e, t) {
		var r = 2 < arguments.length && arguments[2] !== void 0 ? arguments[2] : null;
		if (!t || t.nodeType !== 1 && t.nodeType !== 9 && t.nodeType !== 11) throw Error(n(299));
		return l(e, t, null, r);
	}, e.flushSync = function(e) {
		var t = u.T, n = a.p;
		try {
			if (u.T = null, a.p = 2, e) return e();
		} finally {
			u.T = t, a.p = n, a.d.f();
		}
	}, e.preconnect = function(e, t) {
		typeof e == "string" && (t ? (t = t.crossOrigin, t = typeof t == "string" ? t === "use-credentials" ? t : "" : void 0) : t = null, a.d.C(e, t));
	}, e.prefetchDNS = function(e) {
		typeof e == "string" && a.d.D(e);
	}, e.preinit = function(e, t) {
		if (typeof e == "string" && t && typeof t.as == "string") {
			var n = t.as, r = d(n, t.crossOrigin), i = typeof t.integrity == "string" ? t.integrity : void 0, o = typeof t.fetchPriority == "string" ? t.fetchPriority : void 0;
			n === "style" ? a.d.S(e, typeof t.precedence == "string" ? t.precedence : void 0, {
				crossOrigin: r,
				integrity: i,
				fetchPriority: o
			}) : n === "script" && a.d.X(e, {
				crossOrigin: r,
				integrity: i,
				fetchPriority: o,
				nonce: typeof t.nonce == "string" ? t.nonce : void 0
			});
		}
	}, e.preinitModule = function(e, t) {
		if (typeof e == "string") {
			if (typeof t == "object" && t) {
				if (t.as == null || t.as === "script") {
					var n = d(t.as, t.crossOrigin);
					a.d.M(e, {
						crossOrigin: n,
						integrity: typeof t.integrity == "string" ? t.integrity : void 0,
						nonce: typeof t.nonce == "string" ? t.nonce : void 0,
						fetchPriority: typeof t.fetchPriority == "string" ? t.fetchPriority : void 0
					});
				}
			} else t ?? a.d.M(e);
		}
	}, e.preload = function(e, t) {
		if (typeof e == "string" && typeof t == "object" && t && typeof t.as == "string") {
			var n = t.as, r = d(n, t.crossOrigin);
			a.d.L(e, n, {
				crossOrigin: r,
				integrity: typeof t.integrity == "string" ? t.integrity : void 0,
				nonce: typeof t.nonce == "string" ? t.nonce : void 0,
				type: typeof t.type == "string" ? t.type : void 0,
				fetchPriority: typeof t.fetchPriority == "string" ? t.fetchPriority : void 0,
				referrerPolicy: typeof t.referrerPolicy == "string" ? t.referrerPolicy : void 0,
				imageSrcSet: typeof t.imageSrcSet == "string" ? t.imageSrcSet : void 0,
				imageSizes: typeof t.imageSizes == "string" ? t.imageSizes : void 0,
				media: typeof t.media == "string" ? t.media : void 0
			});
		}
	}, e.preloadModule = function(e, t) {
		if (typeof e == "string") {
			if (t) {
				var n = d(t.as, t.crossOrigin);
				a.d.m(e, {
					as: typeof t.as == "string" && t.as !== "script" ? t.as : void 0,
					crossOrigin: n,
					integrity: typeof t.integrity == "string" ? t.integrity : void 0,
					nonce: typeof t.nonce == "string" ? t.nonce : void 0,
					fetchPriority: typeof t.fetchPriority == "string" ? t.fetchPriority : void 0
				});
			} else a.d.m(e);
		}
	}, e.requestFormReset = function(e) {
		a.d.r(e);
	}, e.unstable_batchedUpdates = function(e, t) {
		return e(t);
	}, e.useFormState = function(e, t, n) {
		return u.H.useFormState(e, t, n);
	}, e.useFormStatus = function() {
		return u.H.useHostTransitionStatus();
	}, e.version = "19.3.1";
})), o = /* @__PURE__ */ e(((e, t) => {
	function n() {
		if (typeof __REACT_DEVTOOLS_GLOBAL_HOOK__ < "u" && typeof __REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE == "function") try {
			__REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE(n);
		} catch (e) {
			console.error(e);
		}
	}
	n(), t.exports = a();
})), s = /* @__PURE__ */ e(((e) => {
	var t = n(), r = i(), a = o();
	function s(e) {
		var t = "https://react.dev/errors/" + e;
		if (1 < arguments.length) {
			t += "?args[]=" + encodeURIComponent(arguments[1]);
			for (var n = 2; n < arguments.length; n++) t += "&args[]=" + encodeURIComponent(arguments[n]);
		}
		return "Minified React error #" + e + "; visit " + t + " for the full message or use the non-minified dev environment for full errors and additional helpful warnings.";
	}
	function c(e) {
		return !(!e || e.nodeType !== 1 && e.nodeType !== 9 && e.nodeType !== 11);
	}
	function l(e) {
		for (var t = e, n = t; n && !n.alternate;) t = n, t.flags & 4098 && (e = t.return), n = t.return;
		for (; t.return;) t = t.return;
		return t.tag === 3 ? e : null;
	}
	function u(e) {
		if (e.tag === 13) {
			var t = e.memoizedState;
			if (t === null && (e = e.alternate, e !== null && (t = e.memoizedState)), t !== null) return t.dehydrated;
		}
		return null;
	}
	function d(e) {
		if (e.tag === 31) {
			var t = e.memoizedState;
			if (t === null && (e = e.alternate, e !== null && (t = e.memoizedState)), t !== null) return t.dehydrated;
		}
		return null;
	}
	function f(e) {
		if (l(e) !== e) throw Error(s(188));
	}
	function p(e) {
		var t = e.alternate;
		if (!t) {
			if (t = l(e), t === null) throw Error(s(188));
			return t === e ? e : null;
		}
		for (var n = e, r = t;;) {
			var i = n.return;
			if (i === null) break;
			var a = i.alternate;
			if (a === null) {
				if (r = i.return, r !== null) {
					n = r;
					continue;
				}
				break;
			}
			if (i.child === a.child) {
				for (a = i.child; a;) {
					if (a === n) return f(i), e;
					if (a === r) return f(i), t;
					a = a.sibling;
				}
				throw Error(s(188));
			}
			if (n.return !== r.return) n = i, r = a;
			else {
				for (var o = !1, c = i.child; c;) {
					if (c === n) {
						o = !0, n = i, r = a;
						break;
					}
					if (c === r) {
						o = !0, r = i, n = a;
						break;
					}
					c = c.sibling;
				}
				if (!o) {
					for (c = a.child; c;) {
						if (c === n) {
							o = !0, n = a, r = i;
							break;
						}
						if (c === r) {
							o = !0, r = a, n = i;
							break;
						}
						c = c.sibling;
					}
					if (!o) throw Error(s(189));
				}
			}
			if (n.alternate !== r) throw Error(s(190));
		}
		if (n.tag !== 3) throw Error(s(188));
		return n.stateNode.current === n ? e : t;
	}
	function m(e) {
		var t = e.tag;
		if (t === 5 || t === 26 || t === 27 || t === 6) return e;
		for (e = e.child; e !== null;) {
			if (t = m(e), t !== null) return t;
			e = e.sibling;
		}
		return null;
	}
	function h(e, t, n, r, i, a) {
		for (; e !== null;) {
			if ((e.tag === 5 || e.tag === 27 || e.tag === 6) && n(e, r, i, a) || (e.tag !== 22 || e.memoizedState === null) && (t || e.tag !== 5 && e.tag !== 27) && h(e.child, t, n, r, i, a)) return !0;
			e = e.sibling;
		}
		return !1;
	}
	function g(e) {
		for (e = e.return; e !== null;) {
			if (e.tag === 3 || e.tag === 5 || e.tag === 27) return e;
			e = e.return;
		}
		return null;
	}
	function _(e) {
		var t = !1;
		for (e = e.return; e !== null && (e.tag === 4 && (t = !0), e.tag !== 3 && e.tag !== 5 && e.tag !== 27);) e = e.return;
		return t;
	}
	function v(e) {
		var t = [null, null], n = g(e);
		return n === null || y(t, e, n.child, { foundSelf: !1 }), t;
	}
	function y(e, t, n, r) {
		for (; n !== null;) {
			if (n === t) r.foundSelf = !0;
			else if (n.tag === 5 || n.tag === 27 || n.tag === 6) {
				if (r.foundSelf) return e[1] = n, !0;
				e[0] = n;
			} else if ((n.tag !== 22 || n.memoizedState === null) && y(e, t, n.child, r)) return !0;
			n = n.sibling;
		}
		return !1;
	}
	function b(e) {
		switch (e.tag) {
			case 5:
			case 27:
			case 6: return e.stateNode;
			case 3: return e.stateNode.containerInfo;
			default: throw Error(s(559));
		}
	}
	var ee = null, x = null;
	function S(e, t, n) {
		return e === n || e === t && (ee = e, !0);
	}
	function te(e, t, n) {
		return e === n ? (x = e, !1) : e === t && (x !== null && (ee = e), !0);
	}
	function C(e) {
		if (e === null) return null;
		do
			e = e === null ? null : e.return;
		while (e && e.tag !== 5 && e.tag !== 27 && e.tag !== 3);
		return e || null;
	}
	function ne(e, t, n) {
		for (var r = 0, i = e; i; i = n(i)) r++;
		i = 0;
		for (var a = t; a; a = n(a)) i++;
		for (; 0 < r - i;) e = n(e), r--;
		for (; 0 < i - r;) t = n(t), i--;
		for (; r--;) {
			if (e === t || t !== null && e === t.alternate) return e;
			e = n(e), t = n(t);
		}
		return null;
	}
	var w = Object.assign, re = Symbol.for("react.element"), T = Symbol.for("react.transitional.element"), E = Symbol.for("react.portal"), D = Symbol.for("react.fragment"), ie = Symbol.for("react.strict_mode"), ae = Symbol.for("react.profiler"), oe = Symbol.for("react.consumer"), se = Symbol.for("react.context"), ce = Symbol.for("react.forward_ref"), O = Symbol.for("react.suspense"), le = Symbol.for("react.suspense_list"), ue = Symbol.for("react.memo"), de = Symbol.for("react.lazy"), fe = Symbol.for("react.activity"), pe = Symbol.for("react.legacy_hidden"), me = Symbol.for("react.memo_cache_sentinel"), he = Symbol.for("react.view_transition"), ge = Symbol.for("react.recoverable"), _e = Symbol.iterator;
	function ve(e) {
		return typeof e != "object" || !e ? null : (e = _e && e[_e] || e["@@iterator"], typeof e == "function" ? e : null);
	}
	var ye = Symbol.for("react.client.reference");
	function be(e) {
		if (e == null) return null;
		if (typeof e == "function") return e.$$typeof === ye ? null : e.displayName || e.name || null;
		if (typeof e == "string") return e;
		switch (e) {
			case D: return "Fragment";
			case ae: return "Profiler";
			case ie: return "StrictMode";
			case O: return "Suspense";
			case le: return "SuspenseList";
			case fe: return "Activity";
			case he: return "ViewTransition";
		}
		if (typeof e == "object") switch (e.$$typeof) {
			case E: return "Portal";
			case se: return e.displayName || "Context";
			case oe: return (e._context.displayName || "Context") + ".Consumer";
			case ce:
				var t = e.render;
				return e = e.displayName, e ||= (e = t.displayName || t.name || "", e === "" ? "ForwardRef" : "ForwardRef(" + e + ")"), e;
			case ue: return t = e.displayName || null, t === null ? be(e.type) || "Memo" : t;
			case de:
				t = e._payload, e = e._init;
				try {
					return be(e(t));
				} catch {}
		}
		return null;
	}
	var xe = Array.isArray, k = r.__CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE, A = a.__DOM_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE, Se = {
		pending: !1,
		data: null,
		method: null,
		action: null
	}, Ce = [], we = -1;
	function j(e) {
		return { current: e };
	}
	function M(e) {
		0 > we || (e.current = Ce[we], Ce[we] = null, we--);
	}
	function N(e, t) {
		we++, Ce[we] = e.current, e.current = t;
	}
	var Te = j(null), Ee = j(null), De = j(null), Oe = j(null);
	function ke(e, t) {
		switch (N(De, t), N(Ee, e), N(Te, null), t.nodeType) {
			case 9:
			case 11:
				e = (e = t.documentElement) && (e = e.namespaceURI) ? up(e) : 0;
				break;
			default: if (e = t.tagName, t = t.namespaceURI) t = up(t), e = dp(t, e);
			else switch (e) {
				case "svg":
					e = 1;
					break;
				case "math":
					e = 2;
					break;
				default: e = 0;
			}
		}
		M(Te), N(Te, e);
	}
	function Ae() {
		M(Te), M(Ee), M(De);
	}
	function je(e) {
		var t = e.memoizedState;
		t !== null && (sh._currentValue = t.memoizedState, N(Oe, e)), t = Te.current;
		var n = dp(t, e.type);
		t !== n && (N(Ee, e), N(Te, n));
	}
	function Me(e) {
		Ee.current === e && (M(Te), M(Ee)), Oe.current === e && (M(Oe), sh._currentValue = Se);
	}
	var Ne, Pe;
	function Fe(e) {
		if (Ne === void 0) try {
			throw Error();
		} catch (e) {
			var t = e.stack.trim().match(/\n( *(at )?)/);
			Ne = t && t[1] || "", Pe = -1 < e.stack.indexOf("\n    at") ? " (<anonymous>)" : -1 < e.stack.indexOf("@") ? "@unknown:0:0" : "";
		}
		return "\n" + Ne + e + Pe;
	}
	var Ie = !1;
	function Le(e, t) {
		if (!e || Ie) return "";
		Ie = !0;
		var n = Error.prepareStackTrace;
		Error.prepareStackTrace = void 0;
		try {
			var r = { DetermineComponentFrameRoot: function() {
				try {
					if (t) {
						var n = function() {
							throw Error();
						};
						if (Object.defineProperty(n.prototype, "props", { set: function() {
							throw Error();
						} }), typeof Reflect == "object" && Reflect.construct) {
							try {
								Reflect.construct(n, []);
							} catch (e) {
								var r = e;
							}
							Reflect.construct(e, [], n);
						} else {
							try {
								n.call();
							} catch (e) {
								r = e;
							}
							n = !1;
							try {
								var i = Object.getOwnPropertyDescriptor(e.prototype, "props");
								Object.defineProperty(e.prototype, "props", {
									configurable: !0,
									set: function() {
										throw Error();
									}
								}), n = !0, new e();
							} finally {
								n && (i === void 0 ? delete e.prototype.props : Object.defineProperty(e.prototype, "props", i));
							}
						}
					} else {
						try {
							throw Error();
						} catch (e) {
							r = e;
						}
						(n = e()) && typeof n.catch == "function" && n.catch(function() {});
					}
				} catch (e) {
					if (e && r && typeof e.stack == "string") return [e.stack, r.stack];
				}
				return [null, null];
			} };
			r.DetermineComponentFrameRoot.displayName = "DetermineComponentFrameRoot";
			var i = Object.getOwnPropertyDescriptor(r.DetermineComponentFrameRoot, "name");
			i && i.configurable && Object.defineProperty(r.DetermineComponentFrameRoot, "name", { value: "DetermineComponentFrameRoot" });
			var a = r.DetermineComponentFrameRoot(), o = a[0], s = a[1];
			if (o && s) {
				var c = o.split("\n"), l = s.split("\n");
				for (i = r = 0; r < c.length && !c[r].includes("DetermineComponentFrameRoot");) r++;
				for (; i < l.length && !l[i].includes("DetermineComponentFrameRoot");) i++;
				if (r === c.length || i === l.length) for (r = c.length - 1, i = l.length - 1; 1 <= r && 0 <= i && c[r] !== l[i];) i--;
				for (; 1 <= r && 0 <= i; r--, i--) if (c[r] !== l[i]) {
					if (r !== 1 || i !== 1) do
						if (r--, i--, 0 > i || c[r] !== l[i]) {
							var u = "\n" + c[r].replace(" at new ", " at ");
							return e.displayName && u.includes("<anonymous>") && (u = u.replace("<anonymous>", e.displayName)), u;
						}
					while (1 <= r && 0 <= i);
					break;
				}
			}
		} finally {
			Ie = !1, Error.prepareStackTrace = n;
		}
		return (n = e ? e.displayName || e.name : "") ? Fe(n) : "";
	}
	function Re(e, t) {
		switch (e.tag) {
			case 26:
			case 27:
			case 5: return Fe(e.type);
			case 16: return Fe("Lazy");
			case 13: return e.child !== t && t !== null ? Fe("Suspense Fallback") : Fe("Suspense");
			case 19: return Fe("SuspenseList");
			case 0:
			case 15: return Le(e.type, !1);
			case 11: return Le(e.type.render, !1);
			case 1: return Le(e.type, !0);
			case 31: return Fe("Activity");
			case 30: return Fe("ViewTransition");
			default: return "";
		}
	}
	function ze(e) {
		try {
			var t = "", n = null;
			do
				t += Re(e, n), n = e, e = e.return;
			while (e);
			return t;
		} catch (e) {
			return "\nError generating stack: " + e.message + "\n" + e.stack;
		}
	}
	var Be = Object.prototype.hasOwnProperty, Ve = t.unstable_scheduleCallback, He = t.unstable_cancelCallback, Ue = t.unstable_shouldYield, We = t.unstable_requestPaint, P = t.unstable_now, Ge = t.unstable_getCurrentPriorityLevel, Ke = t.unstable_ImmediatePriority, qe = t.unstable_UserBlockingPriority, Je = t.unstable_NormalPriority, Ye = t.unstable_LowPriority, Xe = t.unstable_IdlePriority, Ze = t.log, Qe = t.unstable_setDisableYieldValue, $e = null, et = null;
	function tt(e) {
		if (typeof Ze == "function" && Qe(e), et && typeof et.setStrictMode == "function") try {
			et.setStrictMode($e, e);
		} catch {}
	}
	var nt = Math.clz32 ? Math.clz32 : at, rt = Math.log, it = Math.LN2;
	function at(e) {
		return e >>>= 0, e === 0 ? 32 : 31 - (rt(e) / it | 0) | 0;
	}
	var ot = 256, st = 262144, ct = 4194304;
	function lt(e) {
		var t = e & 42;
		if (t !== 0) return t;
		switch (e & -e) {
			case 1: return 1;
			case 2: return 2;
			case 4: return 4;
			case 8: return 8;
			case 16: return 16;
			case 32: return 32;
			case 64: return 64;
			case 128: return 128;
			case 256:
			case 512:
			case 1024:
			case 2048:
			case 4096:
			case 8192:
			case 16384:
			case 32768:
			case 65536:
			case 131072: return e & -e;
			case 262144:
			case 524288:
			case 1048576:
			case 2097152: return e & 3932160;
			case 4194304:
			case 8388608:
			case 16777216:
			case 33554432: return e & 62914560;
			case 67108864: return 67108864;
			case 134217728: return 134217728;
			case 268435456: return 268435456;
			case 536870912: return 536870912;
			case 1073741824: return 0;
			default: return e;
		}
	}
	function ut(e, t, n) {
		var r = e.pendingLanes;
		if (r === 0) return 0;
		var i = 0, a = e.suspendedLanes, o = e.pingedLanes;
		e = e.warmLanes;
		var s = r & 134217727;
		return s === 0 ? (s = r & ~a, s === 0 ? o === 0 ? n || (n = r & ~e, n !== 0 && (i = lt(n))) : i = lt(o) : i = lt(s)) : (r = s & ~a, r === 0 ? (o &= s, o === 0 ? n || (n = s & ~e, n !== 0 && (i = lt(n))) : i = lt(o)) : i = lt(r)), i === 0 ? 0 : t !== 0 && t !== i && (t & a) === 0 && (a = i & -i, n = t & -t, a >= n || a === 32 && n & 4194048) ? t : i;
	}
	function dt(e, t) {
		return (e.pendingLanes & ~(e.suspendedLanes & ~e.pingedLanes) & t) === 0;
	}
	function ft(e, t) {
		t & 8 && (t |= t & 32);
		var n = e.entangledLanes;
		if (n !== 0) for (e = e.entanglements, n &= t; 0 < n;) {
			var r = 31 - nt(n), i = 1 << r;
			t |= e[r], n &= ~i;
		}
		return t;
	}
	function pt(e, t) {
		switch (e) {
			case 1:
			case 2:
			case 4:
			case 8:
			case 64: return t + 250;
			case 16:
			case 32:
			case 128:
			case 256:
			case 512:
			case 1024:
			case 2048:
			case 4096:
			case 8192:
			case 16384:
			case 32768:
			case 65536:
			case 131072:
			case 262144:
			case 524288:
			case 1048576:
			case 2097152: return t + 5e3;
			case 4194304:
			case 8388608:
			case 16777216:
			case 33554432: return -1;
			case 67108864:
			case 134217728:
			case 268435456:
			case 536870912:
			case 1073741824: return -1;
			default: return -1;
		}
	}
	function mt() {
		var e = ct;
		return ct <<= 1, !(ct & 62914560) && (ct = 4194304), e;
	}
	function ht(e) {
		for (var t = [], n = 0; 31 > n; n++) t.push(e);
		return t;
	}
	function gt(e, t) {
		e.pendingLanes |= t, t !== 268435456 && (e.suspendedLanes = 0, e.pingedLanes = 0, e.warmLanes = 0);
	}
	function _t(e, t, n, r, i, a) {
		var o = e.pendingLanes;
		e.pendingLanes = n, e.suspendedLanes = 0, e.pingedLanes = 0, e.warmLanes = 0, e.expiredLanes &= n, e.entangledLanes &= n, e.errorRecoveryDisabledLanes &= n, e.shellSuspendCounter = 0;
		var s = e.entanglements, c = e.expirationTimes, l = e.hiddenUpdates;
		for (n = o & ~n; 0 < n;) {
			var u = 31 - nt(n), d = 1 << u;
			s[u] = 0, c[u] = -1;
			var f = l[u];
			if (f !== null) for (l[u] = null, u = 0; u < f.length; u++) {
				var p = f[u];
				p !== null && (p.lane &= -536870913);
			}
			n &= ~d;
		}
		r !== 0 && vt(e, r, 0), a !== 0 && i === 0 && e.tag !== 0 && (e.suspendedLanes |= a & ~(o & ~t));
	}
	function vt(e, t, n) {
		e.pendingLanes |= t, e.suspendedLanes &= ~t;
		var r = 31 - nt(t);
		e.entangledLanes |= t, e.entanglements[r] = e.entanglements[r] | 1073741824 | n & 261930;
	}
	function yt(e, t) {
		var n = e.entangledLanes |= t;
		for (e = e.entanglements; n;) {
			var r = 31 - nt(n), i = 1 << r;
			i & t | e[r] & t && (e[r] |= t), n &= ~i;
		}
	}
	function bt(e, t) {
		var n = t & -t;
		return n = n & 42 ? 1 : xt(n), (n & (e.suspendedLanes | t)) === 0 ? n : 0;
	}
	function xt(e) {
		switch (e) {
			case 2:
				e = 1;
				break;
			case 8:
				e = 4;
				break;
			case 32:
				e = 16;
				break;
			case 256:
			case 512:
			case 1024:
			case 2048:
			case 4096:
			case 8192:
			case 16384:
			case 32768:
			case 65536:
			case 131072:
			case 262144:
			case 524288:
			case 1048576:
			case 2097152:
			case 4194304:
			case 8388608:
			case 16777216:
			case 33554432:
				e = 128;
				break;
			case 268435456:
				e = 134217728;
				break;
			default: e = 0;
		}
		return e;
	}
	function St(e) {
		return e &= -e, 2 < e ? 8 < e ? e & 134217727 ? 32 : 268435456 : 8 : 2;
	}
	function Ct() {
		var e = A.p;
		return e === 0 ? (e = window.event, e === void 0 ? 32 : Ch(e.type)) : e;
	}
	function wt(e, t) {
		var n = A.p;
		try {
			return A.p = e, t();
		} finally {
			A.p = n;
		}
	}
	var Tt = Math.random().toString(36).slice(2), Et = "__reactFiber$" + Tt, Dt = "__reactProps$" + Tt, Ot = "__reactContainer$" + Tt, kt = "__reactEvents$" + Tt, At = "__reactListeners$" + Tt, jt = "__reactHandles$" + Tt, Mt = "__reactResources$" + Tt, Nt = "__reactMarker$" + Tt, Pt = "__reactLoad$" + Tt;
	function Ft(e) {
		delete e[Et], delete e[Dt], delete e[At], delete e[jt];
	}
	function F(e) {
		var t;
		if (t = e[Et]) return t;
		for (var n = e.parentNode; n;) {
			if (t = n[Ot] || n[Et]) {
				if (n = t.alternate, t.child !== null || n !== null && n.child !== null) for (e = fm(e); e !== null;) {
					if (n = e[Et]) return n;
					e = fm(e);
				}
				return t;
			}
			e = n, n = e.parentNode;
		}
		return null;
	}
	function I(e) {
		if (e = e[Et] || e[Ot]) {
			var t = e.tag;
			if (t === 5 || t === 6 || t === 13 || t === 31 || t === 26 || t === 27 || t === 3) return e;
		}
		return null;
	}
	function It(e) {
		var t = e.tag;
		if (t === 5 || t === 26 || t === 27 || t === 6) return e.stateNode;
		throw Error(s(33));
	}
	function Lt(e) {
		var t = e[Mt];
		return t ||= e[Mt] = {
			hoistableStyles: /* @__PURE__ */ new Map(),
			hoistableScripts: /* @__PURE__ */ new Map()
		}, t;
	}
	function L(e) {
		e[Nt] = !0;
	}
	function R(e) {
		e[Pt] = void 0;
	}
	var Rt = /* @__PURE__ */ new Set(), zt = {};
	function Bt(e, t) {
		Vt(e, t), Vt(e + "Capture", t);
	}
	function Vt(e, t) {
		for (zt[e] = t, e = 0; e < t.length; e++) Rt.add(t[e]);
	}
	var Ht = RegExp("^[:A-Z_a-z\\u00C0-\\u00D6\\u00D8-\\u00F6\\u00F8-\\u02FF\\u0370-\\u037D\\u037F-\\u1FFF\\u200C-\\u200D\\u2070-\\u218F\\u2C00-\\u2FEF\\u3001-\\uD7FF\\uF900-\\uFDCF\\uFDF0-\\uFFFD][:A-Z_a-z\\u00C0-\\u00D6\\u00D8-\\u00F6\\u00F8-\\u02FF\\u0370-\\u037D\\u037F-\\u1FFF\\u200C-\\u200D\\u2070-\\u218F\\u2C00-\\u2FEF\\u3001-\\uD7FF\\uF900-\\uFDCF\\uFDF0-\\uFFFD\\-.0-9\\u00B7\\u0300-\\u036F\\u203F-\\u2040]*$"), Ut = {}, Wt = {};
	function Gt(e) {
		return Be.call(Wt, e) ? !0 : Be.call(Ut, e) ? !1 : Ht.test(e) ? Wt[e] = !0 : (Ut[e] = !0, !1);
	}
	var z = !1;
	function Kt() {
		var e = z;
		return z = !1, e;
	}
	function qt(e, t, n) {
		if (Gt(t)) {
			if (n === null) e.removeAttribute(t);
			else {
				switch (typeof n) {
					case "undefined":
					case "function":
					case "symbol":
						e.removeAttribute(t);
						return;
					case "boolean":
						var r = t.toLowerCase().slice(0, 5);
						if (r !== "data-" && r !== "aria-") {
							e.removeAttribute(t);
							return;
						}
				}
				e.setAttribute(t, n);
			}
		}
	}
	function Jt(e, t, n) {
		if (n === null) e.removeAttribute(t);
		else {
			switch (typeof n) {
				case "undefined":
				case "function":
				case "symbol":
				case "boolean":
					e.removeAttribute(t);
					return;
			}
			e.setAttribute(t, n);
		}
	}
	function Yt(e, t, n, r) {
		if (r === null) e.removeAttribute(n);
		else {
			switch (typeof r) {
				case "undefined":
				case "function":
				case "symbol":
				case "boolean":
					e.removeAttribute(n);
					return;
			}
			e.setAttributeNS(t, n, r);
		}
	}
	function Xt(e) {
		switch (typeof e) {
			case "bigint":
			case "boolean":
			case "number":
			case "string":
			case "undefined": return e;
			case "object": return e;
			default: return "";
		}
	}
	function Zt(e) {
		var t = e.type;
		return (e = e.nodeName) && e.toLowerCase() === "input" && (t === "checkbox" || t === "radio");
	}
	function Qt(e, t, n) {
		var r = Object.getOwnPropertyDescriptor(e.constructor.prototype, t);
		if (!e.hasOwnProperty(t) && r !== void 0 && typeof r.get == "function" && typeof r.set == "function") {
			var i = r.get, a = r.set;
			return Object.defineProperty(e, t, {
				configurable: !0,
				get: function() {
					return i.call(this);
				},
				set: function(e) {
					n = "" + e, a.call(this, e);
				}
			}), Object.defineProperty(e, t, { enumerable: r.enumerable }), {
				getValue: function() {
					return n;
				},
				setValue: function(e) {
					n = "" + e;
				},
				stopTracking: function() {
					e._valueTracker = null, delete e[t];
				}
			};
		}
	}
	function $t(e) {
		if (!e._valueTracker) {
			var t = Zt(e) ? "checked" : "value";
			e._valueTracker = Qt(e, t, "" + e[t]);
		}
	}
	function en(e) {
		if (!e) return !1;
		var t = e._valueTracker;
		if (!t) return !0;
		var n = t.getValue(), r = "";
		return e && (r = Zt(e) ? e.checked ? "true" : "false" : e.value), e = r, e !== n && (t.setValue(e), !0);
	}
	var tn = /[\n"\\]/g;
	function nn(e) {
		return e.replace(tn, function(e) {
			return "\\" + e.charCodeAt(0).toString(16) + " ";
		});
	}
	function rn(e, t, n, r, i, a, o, s) {
		e.name = "", o != null && typeof o != "function" && typeof o != "symbol" && typeof o != "boolean" ? e.type = o : e.removeAttribute("type"), t == null ? o !== "submit" && o !== "reset" || e.removeAttribute("value") : o === "number" ? (t === 0 && e.value === "" || e.value != t) && (e.value = "" + Xt(t)) : e.value !== "" + Xt(t) && (e.value = "" + Xt(t)), t == null ? n == null ? r != null && e.removeAttribute("value") : on(e, Xt(n)) : o === "number" && e.value == t ? on(e, Xt(e.value)) : on(e, Xt(t)), i == null && a != null && (e.defaultChecked = !!a), i != null && (e.checked = i && typeof i != "function" && typeof i != "symbol"), s != null && typeof s != "function" && typeof s != "symbol" && typeof s != "boolean" ? e.name = "" + Xt(s) : e.removeAttribute("name");
	}
	function an(e, t, n, r, i, a, o, s) {
		if (a != null && typeof a != "function" && typeof a != "symbol" && typeof a != "boolean" && (e.type = a), t != null || n != null) {
			if (!(a !== "submit" && a !== "reset" || t != null)) {
				$t(e);
				return;
			}
			n = n == null ? "" : "" + Xt(n), t = t == null ? n : "" + Xt(t), s || t === e.value || (e.value = t), e.defaultValue = t;
		}
		r ??= i, r = typeof r != "function" && typeof r != "symbol" && !!r, e.checked = s ? e.checked : !!r, e.defaultChecked = !!r, o != null && typeof o != "function" && typeof o != "symbol" && typeof o != "boolean" && (e.name = o), $t(e);
	}
	function on(e, t) {
		e.defaultValue !== "" + t && (e.defaultValue = "" + t);
	}
	function sn(e, t, n, r) {
		if (e = e.options, t) {
			t = {};
			for (var i = 0; i < n.length; i++) t["$" + n[i]] = !0;
			for (n = 0; n < e.length; n++) i = t.hasOwnProperty("$" + e[n].value), e[n].selected !== i && (e[n].selected = i), i && r && (e[n].defaultSelected = !0);
		} else {
			for (n = "" + Xt(n), t = null, i = 0; i < e.length; i++) {
				if (e[i].value === n) {
					e[i].selected = !0, r && (e[i].defaultSelected = !0);
					return;
				}
				t !== null || e[i].disabled || (t = e[i]);
			}
			t !== null && (t.selected = !0);
		}
	}
	function cn(e, t, n) {
		t != null && (t = "" + Xt(t), t !== e.value && (e.value = t), n == null) ? e.defaultValue !== t && (e.defaultValue = t) : e.defaultValue = n == null ? "" : "" + Xt(n);
	}
	function ln(e, t, n, r) {
		if (t == null) {
			if (r != null) {
				if (n != null) throw Error(s(92));
				if (xe(r)) {
					if (1 < r.length) throw Error(s(93));
					r = r[0];
				}
				n = r;
			}
			n ??= "", t = n;
		}
		n = Xt(t), e.defaultValue = n, r = e.textContent, r === n && r !== "" && r !== null && (e.value = r), $t(e);
	}
	function un(e, t) {
		if (t) {
			var n = e.firstChild;
			if (n && n === e.lastChild && n.nodeType === 3) {
				n.nodeValue = t;
				return;
			}
		}
		e.textContent = t;
	}
	var dn = new Set("animationIterationCount aspectRatio borderImageOutset borderImageSlice borderImageWidth boxFlex boxFlexGroup boxOrdinalGroup columnCount columns flex flexGrow flexPositive flexShrink flexNegative flexOrder gridArea gridRow gridRowEnd gridRowSpan gridRowStart gridColumn gridColumnEnd gridColumnSpan gridColumnStart fontWeight lineClamp lineHeight opacity order orphans scale tabSize widows zIndex zoom fillOpacity floodOpacity stopOpacity strokeDasharray strokeDashoffset strokeMiterlimit strokeOpacity strokeWidth MozAnimationIterationCount MozBoxFlex MozBoxFlexGroup MozLineClamp msAnimationIterationCount msFlex msZoom msFlexGrow msFlexNegative msFlexOrder msFlexPositive msFlexShrink msGridColumn msGridColumnSpan msGridRow msGridRowSpan WebkitAnimationIterationCount WebkitBoxFlex WebKitBoxFlexGroup WebkitBoxOrdinalGroup WebkitColumnCount WebkitColumns WebkitFlex WebkitFlexGrow WebkitFlexPositive WebkitFlexShrink WebkitLineClamp".split(" "));
	function fn(e, t, n) {
		var r = t.indexOf("--") === 0;
		n == null || typeof n == "boolean" || n === "" ? r ? e.setProperty(t, "") : t === "float" ? e.cssFloat = "" : e[t] = "" : r ? e.setProperty(t, n) : typeof n != "number" || n === 0 || dn.has(t) ? t === "float" ? e.cssFloat = n : e[t] = ("" + n).trim() : e[t] = n + "px";
	}
	function pn(e, t, n) {
		if (t != null && typeof t != "object") throw Error(s(62));
		if (e = e.style, n != null) {
			for (var r in n) !n.hasOwnProperty(r) || t != null && t.hasOwnProperty(r) || (r.indexOf("--") === 0 ? e.setProperty(r, "") : r === "float" ? e.cssFloat = "" : e[r] = "", z = !0);
			for (var i in t) r = t[i], t.hasOwnProperty(i) && n[i] !== r && (fn(e, i, r), z = !0);
		} else for (var a in t) t.hasOwnProperty(a) && fn(e, a, t[a]);
	}
	function mn(e) {
		if (e.indexOf("-") === -1) return !1;
		switch (e) {
			case "annotation-xml":
			case "color-profile":
			case "font-face":
			case "font-face-src":
			case "font-face-uri":
			case "font-face-format":
			case "font-face-name":
			case "missing-glyph": return !1;
			default: return !0;
		}
	}
	var hn = /* @__PURE__ */ new Map([
		["acceptCharset", "accept-charset"],
		["htmlFor", "for"],
		["httpEquiv", "http-equiv"],
		["crossOrigin", "crossorigin"],
		["accentHeight", "accent-height"],
		["alignmentBaseline", "alignment-baseline"],
		["arabicForm", "arabic-form"],
		["baselineShift", "baseline-shift"],
		["capHeight", "cap-height"],
		["clipPath", "clip-path"],
		["clipRule", "clip-rule"],
		["colorInterpolation", "color-interpolation"],
		["colorInterpolationFilters", "color-interpolation-filters"],
		["colorProfile", "color-profile"],
		["colorRendering", "color-rendering"],
		["dominantBaseline", "dominant-baseline"],
		["enableBackground", "enable-background"],
		["fillOpacity", "fill-opacity"],
		["fillRule", "fill-rule"],
		["floodColor", "flood-color"],
		["floodOpacity", "flood-opacity"],
		["fontFamily", "font-family"],
		["fontSize", "font-size"],
		["fontSizeAdjust", "font-size-adjust"],
		["fontStretch", "font-stretch"],
		["fontStyle", "font-style"],
		["fontVariant", "font-variant"],
		["fontWeight", "font-weight"],
		["glyphName", "glyph-name"],
		["glyphOrientationHorizontal", "glyph-orientation-horizontal"],
		["glyphOrientationVertical", "glyph-orientation-vertical"],
		["horizAdvX", "horiz-adv-x"],
		["horizOriginX", "horiz-origin-x"],
		["imageRendering", "image-rendering"],
		["letterSpacing", "letter-spacing"],
		["lightingColor", "lighting-color"],
		["markerEnd", "marker-end"],
		["markerMid", "marker-mid"],
		["markerStart", "marker-start"],
		["maskType", "mask-type"],
		["overlinePosition", "overline-position"],
		["overlineThickness", "overline-thickness"],
		["paintOrder", "paint-order"],
		["panose-1", "panose-1"],
		["pointerEvents", "pointer-events"],
		["renderingIntent", "rendering-intent"],
		["shapeRendering", "shape-rendering"],
		["stopColor", "stop-color"],
		["stopOpacity", "stop-opacity"],
		["strikethroughPosition", "strikethrough-position"],
		["strikethroughThickness", "strikethrough-thickness"],
		["strokeDasharray", "stroke-dasharray"],
		["strokeDashoffset", "stroke-dashoffset"],
		["strokeLinecap", "stroke-linecap"],
		["strokeLinejoin", "stroke-linejoin"],
		["strokeMiterlimit", "stroke-miterlimit"],
		["strokeOpacity", "stroke-opacity"],
		["strokeWidth", "stroke-width"],
		["textAnchor", "text-anchor"],
		["textDecoration", "text-decoration"],
		["textRendering", "text-rendering"],
		["transformOrigin", "transform-origin"],
		["underlinePosition", "underline-position"],
		["underlineThickness", "underline-thickness"],
		["unicodeBidi", "unicode-bidi"],
		["unicodeRange", "unicode-range"],
		["unitsPerEm", "units-per-em"],
		["vAlphabetic", "v-alphabetic"],
		["vHanging", "v-hanging"],
		["vIdeographic", "v-ideographic"],
		["vMathematical", "v-mathematical"],
		["vectorEffect", "vector-effect"],
		["vertAdvY", "vert-adv-y"],
		["vertOriginX", "vert-origin-x"],
		["vertOriginY", "vert-origin-y"],
		["wordSpacing", "word-spacing"],
		["writingMode", "writing-mode"],
		["xmlnsXlink", "xmlns:xlink"],
		["xHeight", "x-height"]
	]), gn = /^[\u0000-\u001F ]*j[\r\n\t]*a[\r\n\t]*v[\r\n\t]*a[\r\n\t]*s[\r\n\t]*c[\r\n\t]*r[\r\n\t]*i[\r\n\t]*p[\r\n\t]*t[\r\n\t]*:/i;
	function _n(e) {
		return gn.test("" + e) ? "javascript:throw new Error('React has blocked a javascript: URL as a security precaution.')" : e;
	}
	function vn() {}
	var yn = null;
	function bn(e) {
		return e = e.target || e.srcElement || window, e.correspondingUseElement && (e = e.correspondingUseElement), e.nodeType === 3 ? e.parentNode : e;
	}
	var xn = null, Sn = null;
	function Cn(e) {
		var t = I(e);
		if (t && (e = t.stateNode)) {
			var n = e[Dt] || null;
			a: switch (e = t.stateNode, t.type) {
				case "input":
					if (rn(e, n.value, n.defaultValue, n.defaultValue, n.checked, n.defaultChecked, n.type, n.name), t = n.name, n.type === "radio" && t != null) {
						for (n = e; n.parentNode;) n = n.parentNode;
						for (n = n.querySelectorAll("input[name=\"" + nn("" + t) + "\"][type=\"radio\"]"), t = 0; t < n.length; t++) {
							var r = n[t];
							if (r !== e && r.form === e.form) {
								var i = r[Dt] || null;
								if (!i) throw Error(s(90));
								rn(r, i.value, i.defaultValue, i.defaultValue, i.checked, i.defaultChecked, i.type, i.name);
							}
						}
						for (t = 0; t < n.length; t++) r = n[t], r.form === e.form && en(r);
					}
					break a;
				case "textarea":
					cn(e, n.value, n.defaultValue);
					break a;
				case "select": t = n.value, t != null && sn(e, !!n.multiple, t, !1);
			}
		}
	}
	var wn = !1;
	function Tn(e, t, n) {
		if (wn) return e(t, n);
		wn = !0;
		try {
			return e(t);
		} finally {
			if (wn = !1, (xn !== null || Sn !== null) && (zd(), xn && (t = xn, e = Sn, Sn = xn = null, Cn(t), e))) for (t = 0; t < e.length; t++) Cn(e[t]);
		}
	}
	function En(e, t) {
		var n = e.stateNode;
		if (n === null) return null;
		var r = n[Dt] || null;
		if (r === null) return null;
		n = r[t];
		a: switch (t) {
			case "onClick":
			case "onClickCapture":
			case "onDoubleClick":
			case "onDoubleClickCapture":
			case "onMouseDown":
			case "onMouseDownCapture":
			case "onMouseMove":
			case "onMouseMoveCapture":
			case "onMouseUp":
			case "onMouseUpCapture":
			case "onMouseEnter":
				(r = !r.disabled) || (e = e.type, r = e !== "button" && e !== "input" && e !== "select" && e !== "textarea"), e = !r;
				break a;
			default: e = !1;
		}
		if (e) return null;
		if (n && typeof n != "function") throw Error(s(231, t, typeof n));
		return n;
	}
	var Dn = typeof window < "u" && window.document !== void 0 && window.document.createElement !== void 0, On = !1;
	if (Dn) try {
		var kn = {};
		Object.defineProperty(kn, "passive", { get: function() {
			On = !0;
		} }), window.addEventListener("test", kn, kn), window.removeEventListener("test", kn, kn);
	} catch {
		On = !1;
	}
	var An = null, jn = null, Mn = null;
	function Nn() {
		if (Mn) return Mn;
		var e, t = jn, n = t.length, r, i = "value" in An ? An.value : An.textContent, a = i.length;
		for (e = 0; e < n && t[e] === i[e]; e++);
		var o = n - e;
		for (r = 1; r <= o && t[n - r] === i[a - r]; r++);
		return Mn = i.slice(e, 1 < r ? 1 - r : void 0);
	}
	function Pn(e) {
		var t = e.keyCode;
		return "charCode" in e ? (e = e.charCode, e === 0 && t === 13 && (e = 13)) : e = t, e === 10 && (e = 13), 32 <= e || e === 13 ? e : 0;
	}
	function Fn() {
		return !0;
	}
	function In() {
		return !1;
	}
	function Ln(e) {
		function t(t, n, r, i, a) {
			for (var o in this._reactName = t, this._targetInst = r, this.type = n, this.nativeEvent = i, this.target = a, this.currentTarget = null, e) e.hasOwnProperty(o) && (t = e[o], this[o] = t ? t(i) : i[o]);
			return this.isDefaultPrevented = (i.defaultPrevented == null ? !1 === i.returnValue : i.defaultPrevented) ? Fn : In, this.isPropagationStopped = In, this;
		}
		return w(t.prototype, {
			preventDefault: function() {
				this.defaultPrevented = !0;
				var e = this.nativeEvent;
				e && (e.preventDefault ? e.preventDefault() : typeof e.returnValue != "unknown" && (e.returnValue = !1), this.isDefaultPrevented = Fn);
			},
			stopPropagation: function() {
				var e = this.nativeEvent;
				e && (e.stopPropagation ? e.stopPropagation() : typeof e.cancelBubble != "unknown" && (e.cancelBubble = !0), this.isPropagationStopped = Fn);
			},
			persist: function() {},
			isPersistent: Fn
		}), t;
	}
	var Rn = {
		eventPhase: 0,
		bubbles: 0,
		cancelable: 0,
		timeStamp: function(e) {
			return e.timeStamp || Date.now();
		},
		defaultPrevented: 0,
		isTrusted: 0
	}, zn = Ln(Rn), Bn = w({}, Rn, {
		view: 0,
		detail: 0
	}), Vn = Ln(Bn), Hn, Un, Wn, Gn = w({}, Bn, {
		screenX: 0,
		screenY: 0,
		clientX: 0,
		clientY: 0,
		pageX: 0,
		pageY: 0,
		ctrlKey: 0,
		shiftKey: 0,
		altKey: 0,
		metaKey: 0,
		getModifierState: nr,
		button: 0,
		buttons: 0,
		relatedTarget: function(e) {
			return e.relatedTarget === void 0 ? e.fromElement === e.srcElement ? e.toElement : e.fromElement : e.relatedTarget;
		},
		movementX: function(e) {
			return "movementX" in e ? e.movementX : (e !== Wn && (Wn && e.type === "mousemove" ? (Hn = e.screenX - Wn.screenX, Un = e.screenY - Wn.screenY) : Un = Hn = 0, Wn = e), Hn);
		},
		movementY: function(e) {
			return "movementY" in e ? e.movementY : Un;
		}
	}), Kn = Ln(Gn), qn = Ln(w({}, Gn, { dataTransfer: 0 })), Jn = Ln(w({}, Bn, { relatedTarget: 0 })), Yn = Ln(w({}, Rn, {
		animationName: 0,
		elapsedTime: 0,
		pseudoElement: 0
	})), Xn = Ln(w({}, Rn, { clipboardData: function(e) {
		return "clipboardData" in e ? e.clipboardData : window.clipboardData;
	} })), Zn = Ln(w({}, Rn, { data: 0 })), Qn = {
		Esc: "Escape",
		Spacebar: " ",
		Left: "ArrowLeft",
		Up: "ArrowUp",
		Right: "ArrowRight",
		Down: "ArrowDown",
		Del: "Delete",
		Win: "OS",
		Menu: "ContextMenu",
		Apps: "ContextMenu",
		Scroll: "ScrollLock",
		MozPrintableKey: "Unidentified"
	}, $n = {
		8: "Backspace",
		9: "Tab",
		12: "Clear",
		13: "Enter",
		16: "Shift",
		17: "Control",
		18: "Alt",
		19: "Pause",
		20: "CapsLock",
		27: "Escape",
		32: " ",
		33: "PageUp",
		34: "PageDown",
		35: "End",
		36: "Home",
		37: "ArrowLeft",
		38: "ArrowUp",
		39: "ArrowRight",
		40: "ArrowDown",
		45: "Insert",
		46: "Delete",
		112: "F1",
		113: "F2",
		114: "F3",
		115: "F4",
		116: "F5",
		117: "F6",
		118: "F7",
		119: "F8",
		120: "F9",
		121: "F10",
		122: "F11",
		123: "F12",
		144: "NumLock",
		145: "ScrollLock",
		224: "Meta"
	}, er = {
		Alt: "altKey",
		Control: "ctrlKey",
		Meta: "metaKey",
		Shift: "shiftKey"
	};
	function tr(e) {
		var t = this.nativeEvent;
		return t.getModifierState ? t.getModifierState(e) : (e = er[e]) ? !!t[e] : !1;
	}
	function nr() {
		return tr;
	}
	var rr = Ln(w({}, Bn, {
		key: function(e) {
			if (e.key) {
				var t = Qn[e.key] || e.key;
				if (t !== "Unidentified") return t;
			}
			return e.type === "keypress" ? (e = Pn(e), e === 13 ? "Enter" : String.fromCharCode(e)) : e.type === "keydown" || e.type === "keyup" ? $n[e.keyCode] || "Unidentified" : "";
		},
		code: 0,
		location: 0,
		ctrlKey: 0,
		shiftKey: 0,
		altKey: 0,
		metaKey: 0,
		repeat: 0,
		locale: 0,
		getModifierState: nr,
		charCode: function(e) {
			return e.type === "keypress" ? Pn(e) : 0;
		},
		keyCode: function(e) {
			return e.type === "keydown" || e.type === "keyup" ? e.keyCode : 0;
		},
		which: function(e) {
			return e.type === "keypress" ? Pn(e) : e.type === "keydown" || e.type === "keyup" ? e.keyCode : 0;
		}
	})), ir = Ln(w({}, Gn, {
		pointerId: 0,
		width: 0,
		height: 0,
		pressure: 0,
		tangentialPressure: 0,
		tiltX: 0,
		tiltY: 0,
		twist: 0,
		pointerType: 0,
		isPrimary: 0
	})), ar = Ln(w({}, Rn, { submitter: 0 })), or = Ln(w({}, Bn, {
		touches: 0,
		targetTouches: 0,
		changedTouches: 0,
		altKey: 0,
		metaKey: 0,
		ctrlKey: 0,
		shiftKey: 0,
		getModifierState: nr
	})), sr = Ln(w({}, Rn, {
		propertyName: 0,
		elapsedTime: 0,
		pseudoElement: 0
	})), cr = Ln(w({}, Gn, {
		deltaX: function(e) {
			return "deltaX" in e ? e.deltaX : "wheelDeltaX" in e ? -e.wheelDeltaX : 0;
		},
		deltaY: function(e) {
			return "deltaY" in e ? e.deltaY : "wheelDeltaY" in e ? -e.wheelDeltaY : "wheelDelta" in e ? -e.wheelDelta : 0;
		},
		deltaZ: 0,
		deltaMode: 0
	})), lr = Ln(w({}, Rn, {
		newState: 0,
		oldState: 0,
		source: 0
	})), ur = [
		9,
		13,
		27,
		32
	], dr = Dn && "CompositionEvent" in window, fr = null;
	Dn && "documentMode" in document && (fr = document.documentMode);
	var pr = Dn && "TextEvent" in window && !fr, mr = Dn && (!dr || fr && 8 < fr && 11 >= fr), hr = " ", gr = !1;
	function _r(e, t) {
		switch (e) {
			case "keyup": return ur.indexOf(t.keyCode) !== -1;
			case "keydown": return t.keyCode !== 229;
			case "keypress":
			case "mousedown":
			case "focusout": return !0;
			default: return !1;
		}
	}
	function vr(e) {
		return e = e.detail, typeof e == "object" && "data" in e ? e.data : null;
	}
	var yr = !1;
	function br(e, t) {
		switch (e) {
			case "compositionend": return vr(t);
			case "keypress": return t.which === 32 ? (gr = !0, hr) : null;
			case "textInput": return e = t.data, e === hr && gr ? null : e;
			default: return null;
		}
	}
	function xr(e, t) {
		if (yr) return e === "compositionend" || !dr && _r(e, t) ? (e = Nn(), Mn = jn = An = null, yr = !1, e) : null;
		switch (e) {
			case "paste": return null;
			case "keypress":
				if (!(t.ctrlKey || t.altKey || t.metaKey) || t.ctrlKey && t.altKey) {
					if (t.char && 1 < t.char.length) return t.char;
					if (t.which) return String.fromCharCode(t.which);
				}
				return null;
			case "compositionend": return mr && t.locale !== "ko" ? null : t.data;
			default: return null;
		}
	}
	var Sr = {
		color: !0,
		date: !0,
		datetime: !0,
		"datetime-local": !0,
		email: !0,
		month: !0,
		number: !0,
		password: !0,
		range: !0,
		search: !0,
		tel: !0,
		text: !0,
		time: !0,
		url: !0,
		week: !0
	};
	function Cr(e) {
		var t = e && e.nodeName && e.nodeName.toLowerCase();
		return t === "input" ? !!Sr[e.type] : t === "textarea";
	}
	function wr(e, t, n, r) {
		xn ? Sn ? Sn.push(r) : Sn = [r] : xn = r, t = Jf(t, "onChange"), 0 < t.length && (n = new zn("onChange", "change", null, n, r), e.push({
			event: n,
			listeners: t
		}));
	}
	var Tr = null, Er = null;
	function Dr(e) {
		Vf(e, 0);
	}
	function Or(e) {
		if (en(It(e))) return e;
	}
	function kr(e, t) {
		if (e === "change") return t;
	}
	var Ar = !1;
	if (Dn) {
		var jr;
		if (Dn) {
			var Mr = "oninput" in document;
			if (!Mr) {
				var Nr = document.createElement("div");
				Nr.setAttribute("oninput", "return;"), Mr = typeof Nr.oninput == "function";
			}
			jr = Mr;
		} else jr = !1;
		Ar = jr && (!document.documentMode || 9 < document.documentMode);
	}
	function Pr() {
		Tr && (Tr.detachEvent("onpropertychange", Fr), Er = Tr = null);
	}
	function Fr(e) {
		if (e.propertyName === "value" && Or(Er)) {
			var t = [];
			wr(t, Er, e, bn(e)), Tn(Dr, t);
		}
	}
	function Ir(e, t, n) {
		e === "focusin" ? (Pr(), Tr = t, Er = n, Tr.attachEvent("onpropertychange", Fr)) : e === "focusout" && Pr();
	}
	function Lr(e) {
		if (e === "selectionchange" || e === "keyup" || e === "keydown") return Or(Er);
	}
	function Rr(e, t) {
		if (e === "click") return Or(t);
	}
	function zr(e, t) {
		if (e === "input" || e === "change") return Or(t);
	}
	function Br(e, t) {
		return e === t && (e !== 0 || 1 / e == 1 / t) || e !== e && t !== t;
	}
	var Vr = typeof Object.is == "function" ? Object.is : Br;
	function Hr(e, t) {
		if (Vr(e, t)) return !0;
		if (typeof e != "object" || !e || typeof t != "object" || !t) return !1;
		var n = Object.keys(e), r = Object.keys(t);
		if (n.length !== r.length) return !1;
		for (r = 0; r < n.length; r++) {
			var i = n[r];
			if (!Be.call(t, i) || !Vr(e[i], t[i])) return !1;
		}
		return !0;
	}
	function Ur(e) {
		if (e ||= typeof document < "u" ? document : void 0, e === void 0) return null;
		try {
			return e.activeElement || e.body;
		} catch {
			return e.body;
		}
	}
	function Wr(e) {
		for (; e && e.firstChild;) e = e.firstChild;
		return e;
	}
	function Gr(e, t) {
		var n = Wr(e);
		e = 0;
		for (var r; n;) {
			if (n.nodeType === 3) {
				if (r = e + n.textContent.length, e <= t && r >= t) return {
					node: n,
					offset: t - e
				};
				e = r;
			}
			a: {
				for (; n;) {
					if (n.nextSibling) {
						n = n.nextSibling;
						break a;
					}
					n = n.parentNode;
				}
				n = void 0;
			}
			n = Wr(n);
		}
	}
	function Kr(e, t) {
		return e && t ? e === t ? !0 : e && e.nodeType === 3 ? !1 : t && t.nodeType === 3 ? Kr(e, t.parentNode) : "contains" in e ? e.contains(t) : e.compareDocumentPosition ? !!(e.compareDocumentPosition(t) & 16) : !1 : !1;
	}
	function qr(e) {
		e = e != null && e.ownerDocument != null && e.ownerDocument.defaultView != null ? e.ownerDocument.defaultView : window;
		for (var t = Ur(e.document); t instanceof e.HTMLIFrameElement;) {
			try {
				var n = typeof t.contentWindow.location.href == "string";
			} catch {
				n = !1;
			}
			if (n) e = t.contentWindow;
			else break;
			t = Ur(e.document);
		}
		return t;
	}
	function Jr(e) {
		var t = e && e.nodeName && e.nodeName.toLowerCase();
		return t && (t === "input" && (e.type === "text" || e.type === "search" || e.type === "tel" || e.type === "url" || e.type === "password") || t === "textarea" || e.contentEditable === "true");
	}
	var Yr = Dn && "documentMode" in document && 11 >= document.documentMode, Xr = null, Zr = null, Qr = null, $r = !1;
	function ei(e, t, n) {
		var r = n.window === n ? n.document : n.nodeType === 9 ? n : n.ownerDocument;
		$r || Xr == null || Xr !== Ur(r) || (r = Xr, "selectionStart" in r && Jr(r) ? r = {
			start: r.selectionStart,
			end: r.selectionEnd
		} : (r = (r.ownerDocument && r.ownerDocument.defaultView || window).getSelection(), r = {
			anchorNode: r.anchorNode,
			anchorOffset: r.anchorOffset,
			focusNode: r.focusNode,
			focusOffset: r.focusOffset
		}), Qr && Hr(Qr, r) || (Qr = r, r = Jf(Zr, "onSelect"), 0 < r.length && (t = new zn("onSelect", "select", null, t, n), e.push({
			event: t,
			listeners: r
		}), t.target = Xr)));
	}
	function ti(e, t) {
		var n = {};
		return n[e.toLowerCase()] = t.toLowerCase(), n["Webkit" + e] = "webkit" + t, n["Moz" + e] = "moz" + t, n;
	}
	var ni = {
		animationend: ti("Animation", "AnimationEnd"),
		animationiteration: ti("Animation", "AnimationIteration"),
		animationstart: ti("Animation", "AnimationStart"),
		transitionrun: ti("Transition", "TransitionRun"),
		transitionstart: ti("Transition", "TransitionStart"),
		transitioncancel: ti("Transition", "TransitionCancel"),
		transitionend: ti("Transition", "TransitionEnd")
	}, ri = {}, ii = {};
	Dn && (ii = document.createElement("div").style, "AnimationEvent" in window || (delete ni.animationend.animation, delete ni.animationiteration.animation, delete ni.animationstart.animation), "TransitionEvent" in window || delete ni.transitionend.transition);
	function ai(e) {
		if (ri[e]) return ri[e];
		if (!ni[e]) return e;
		var t = ni[e], n;
		for (n in t) if (t.hasOwnProperty(n) && n in ii) return ri[e] = t[n];
		return e;
	}
	var oi = ai("animationend"), si = ai("animationiteration"), ci = ai("animationstart"), li = ai("transitionrun"), ui = ai("transitionstart"), di = ai("transitioncancel"), fi = ai("transitionend"), pi = /* @__PURE__ */ new Map(), mi = "abort auxClick beforeToggle cancel canPlay canPlayThrough click close contextMenu copy cut drag dragEnd dragEnter dragExit dragLeave dragOver dragStart drop durationChange emptied encrypted ended error fullscreenChange fullscreenError gotPointerCapture input invalid keyDown keyPress keyUp load loadedData loadedMetadata loadStart lostPointerCapture mouseDown mouseMove mouseOut mouseOver mouseUp paste pause play playing pointerCancel pointerDown pointerMove pointerOut pointerOver pointerUp progress rateChange reset resize seeked seeking stalled submit suspend timeUpdate touchCancel touchEnd touchStart volumeChange scroll toggle touchMove waiting wheel".split(" ");
	mi.push("scrollEnd");
	function hi(e, t) {
		pi.set(e, t), Bt(t, [e]);
	}
	var gi = 0;
	function _i(e, t) {
		if (e.name != null && e.name !== "auto") return e.name;
		if (t.autoName !== null) return t.autoName;
		e = bd.identifierPrefix;
		var n = gi++;
		return e = "_" + e + "t_" + n.toString(32) + "_", t.autoName = e;
	}
	function vi(e) {
		if (e == null || typeof e == "string") return e;
		var t = null, n = Od;
		if (n !== null) for (var r = 0; r < n.length; r++) {
			var i = e[n[r]];
			if (i != null) {
				if (i === "none") return "none";
				t = t == null ? i : t + (" " + i);
			}
		}
		return t ?? e.default;
	}
	function yi(e, t) {
		return e = vi(e), t = vi(t), t == null ? e === "auto" ? null : e : t === "auto" ? null : t;
	}
	var bi = typeof reportError == "function" ? reportError : function(e) {
		if (typeof window == "object" && typeof window.ErrorEvent == "function") {
			var t = new window.ErrorEvent("error", {
				bubbles: !0,
				cancelable: !0,
				message: typeof e == "object" && e && typeof e.message == "string" ? String(e.message) : String(e),
				error: e
			});
			if (!window.dispatchEvent(t)) return;
		} else if (typeof process == "object" && typeof process.emit == "function") {
			process.emit("uncaughtException", e);
			return;
		}
		console.error(e);
	}, xi = [], Si = 0, Ci = 0;
	function wi() {
		for (var e = Si, t = Ci = Si = 0; t < e;) {
			var n = xi[t];
			xi[t++] = null;
			var r = xi[t];
			xi[t++] = null;
			var i = xi[t];
			xi[t++] = null;
			var a = xi[t];
			if (xi[t++] = null, r !== null && i !== null) {
				var o = r.pending;
				o === null ? i.next = i : (i.next = o.next, o.next = i), r.pending = i;
			}
			a !== 0 && Oi(n, i, a);
		}
	}
	function Ti(e, t, n, r) {
		xi[Si++] = e, xi[Si++] = t, xi[Si++] = n, xi[Si++] = r, Ci |= r, e.lanes |= r, e = e.alternate, e !== null && (e.lanes |= r);
	}
	function Ei(e, t, n, r) {
		return Ti(e, t, n, r), ki(e);
	}
	function Di(e, t) {
		return Ti(e, null, null, t), ki(e);
	}
	function Oi(e, t, n) {
		e.lanes |= n;
		var r = e.alternate;
		r !== null && (r.lanes |= n);
		for (var i = !1, a = e.return; a !== null;) a.childLanes |= n, r = a.alternate, r !== null && (r.childLanes |= n), a.tag === 22 && (e = a.stateNode, e === null || e._visibility & 1 || (i = !0)), e = a, a = a.return;
		return e.tag === 3 ? (a = e.stateNode, i && t !== null && (i = 31 - nt(n), e = a.hiddenUpdates, r = e[i], r === null ? e[i] = [t] : r.push(t), t.lane = n | 536870912), a) : null;
	}
	function ki(e) {
		if (50 < kd) throw kd = 0, Ad = null, Error(s(185));
		for (var t = e.return; t !== null;) e = t, t = e.return;
		return e.tag === 3 ? e.stateNode : null;
	}
	var Ai = {};
	function ji(e, t, n, r) {
		this.tag = e, this.key = n, this.sibling = this.child = this.return = this.stateNode = this.type = this.elementType = null, this.index = 0, this.refCleanup = this.ref = null, this.pendingProps = t, this.dependencies = this.memoizedState = this.updateQueue = this.memoizedProps = null, this.mode = r, this.subtreeFlags = this.flags = 0, this.deletions = null, this.childLanes = this.lanes = 0, this.alternate = null;
	}
	function Mi(e, t, n, r) {
		return new ji(e, t, n, r);
	}
	function Ni(e) {
		return e = e.prototype, !(!e || !e.isReactComponent);
	}
	function Pi(e, t) {
		var n = e.alternate;
		return n === null ? (n = Mi(e.tag, t, e.key, e.mode), n.elementType = e.elementType, n.type = e.type, n.stateNode = e.stateNode, n.alternate = e, e.alternate = n) : (n.pendingProps = t, n.type = e.type, n.flags = 0, n.subtreeFlags = 0, n.deletions = null), n.flags = e.flags & 1206910976, n.childLanes = e.childLanes, n.lanes = e.lanes, n.child = e.child, n.memoizedProps = e.memoizedProps, n.memoizedState = e.memoizedState, n.updateQueue = e.updateQueue, t = e.dependencies, n.dependencies = t === null ? null : {
			lanes: t.lanes,
			firstContext: t.firstContext
		}, n.sibling = e.sibling, n.index = e.index, n.ref = e.ref, n.refCleanup = e.refCleanup, n;
	}
	function Fi(e, t) {
		e.flags &= 1206910978;
		var n = e.alternate;
		return n === null ? (e.childLanes = 0, e.lanes = t, e.child = null, e.subtreeFlags = 0, e.memoizedProps = null, e.memoizedState = null, e.updateQueue = null, e.dependencies = null, e.stateNode = null) : (e.childLanes = n.childLanes, e.lanes = n.lanes, e.child = n.child, e.subtreeFlags = 0, e.deletions = null, e.memoizedProps = n.memoizedProps, e.memoizedState = n.memoizedState, e.updateQueue = n.updateQueue, e.type = n.type, t = n.dependencies, e.dependencies = t === null ? null : {
			lanes: t.lanes,
			firstContext: t.firstContext
		}), e;
	}
	function Ii(e, t, n, r, i, a) {
		var o = 0;
		if (r = e, typeof r == "function") Ni(r) && (o = 1);
		else if (typeof r == "string") o = qm(e, n, Te.current) ? 26 : e === "html" || e === "head" || e === "body" ? 27 : 5;
		else a: switch (r) {
			case fe: return e = Mi(31, n, t, i), e.elementType = fe, e.lanes = a, e;
			case D: return Li(n.children, i, a, t);
			case ie:
				o = 8, i |= 24;
				break;
			case ae: return e = Mi(12, n, t, i | 2), e.elementType = ae, e.lanes = a, e;
			case O: return e = Mi(13, n, t, i), e.elementType = O, e.lanes = a, e;
			case le: return e = Mi(19, n, t, i), e.elementType = le, e.lanes = a, e;
			case pe:
			case he: return e = i | 32, e = Mi(30, n, t, e), e.elementType = he, e.lanes = a, e.stateNode = {
				autoName: null,
				paired: null,
				clones: null,
				ref: null
			}, e;
			default:
				if (typeof r == "object" && r) switch (r.$$typeof) {
					case se:
						o = 10;
						break a;
					case oe:
						o = 9;
						break a;
					case ce:
						o = 11;
						break a;
					case ue:
						o = 14;
						break a;
					case de:
						o = 16, r = null;
						break a;
				}
				o = 29, n = Error(s(130, e === null ? "null" : typeof e, "")), r = null;
		}
		return t = Mi(o, n, t, i), t.elementType = e, t.type = r, t.lanes = a, t;
	}
	function Li(e, t, n, r) {
		return e = Mi(7, e, r, t), e.lanes = n, e;
	}
	function Ri(e, t, n) {
		return e = Mi(6, e, null, t), e.lanes = n, e;
	}
	function zi(e) {
		var t = Mi(18, null, null, 0);
		return t.stateNode = e, t;
	}
	function Bi(e, t, n) {
		return t = Mi(4, e.children === null ? [] : e.children, e.key, t), t.lanes = n, t.stateNode = {
			containerInfo: e.containerInfo,
			pendingChildren: null,
			implementation: e.implementation
		}, t;
	}
	var Vi = /* @__PURE__ */ new WeakMap();
	function Hi(e, t) {
		if (typeof e == "object" && e) {
			var n = Vi.get(e);
			return n === void 0 ? (t = {
				value: e,
				source: t,
				stack: ze(t)
			}, Vi.set(e, t), t) : n;
		}
		return {
			value: e,
			source: t,
			stack: ze(t)
		};
	}
	var Ui = [], Wi = 0, Gi = null, Ki = 0, qi = [], Ji = 0, Yi = null, Xi = 1, Zi = "";
	function Qi(e, t) {
		Ui[Wi++] = Ki, Ui[Wi++] = Gi, Gi = e, Ki = t;
	}
	function $i(e, t, n) {
		qi[Ji++] = Xi, qi[Ji++] = Zi, qi[Ji++] = Yi, Yi = e;
		var r = Xi;
		e = Zi;
		var i = 32 - nt(r) - 1;
		r &= ~(1 << i), n += 1;
		var a = 32 - nt(t) + i;
		if (30 < a) {
			var o = i - i % 5;
			a = (r & (1 << o) - 1).toString(32), r >>= o, i -= o, Xi = 1 << 32 - nt(t) + i | n << i | r, Zi = a + e;
		} else Xi = 1 << a | n << i | r, Zi = e;
	}
	function ea(e) {
		e.return !== null && (Qi(e, 1), $i(e, 1, 0));
	}
	function ta(e) {
		for (; e === Gi;) Gi = Ui[--Wi], Ui[Wi] = null, Ki = Ui[--Wi], Ui[Wi] = null;
		for (; e === Yi;) Yi = qi[--Ji], qi[Ji] = null, Zi = qi[--Ji], qi[Ji] = null, Xi = qi[--Ji], qi[Ji] = null;
	}
	function na(e, t) {
		qi[Ji++] = Xi, qi[Ji++] = Zi, qi[Ji++] = Yi, Xi = t.id, Zi = t.overflow, Yi = e;
	}
	var ra = null, B = null, V = !1, ia = null, aa = !1, oa = Error(s(519));
	function sa(e) {
		throw pa(Hi(Error(s(418, 1 < arguments.length && arguments[1] !== void 0 && arguments[1] ? "text" : "HTML", "")), e)), oa;
	}
	function ca(e) {
		var t = e.stateNode, n = e.type, r = e.memoizedProps;
		switch (t[Et] = e, t[Dt] = r, n) {
			case "dialog":
				Q("cancel", t), Q("close", t);
				break;
			case "iframe":
			case "object":
			case "embed":
				Q("load", t);
				break;
			case "video":
			case "audio":
				for (n = 0; n < zf.length; n++) Q(zf[n], t);
				break;
			case "source":
				Q("error", t);
				break;
			case "img":
			case "image":
			case "link":
				Q("error", t), Q("load", t);
				break;
			case "details":
				Q("toggle", t);
				break;
			case "input":
				Q("invalid", t), an(t, r.value, r.defaultValue, r.checked, r.defaultChecked, r.type, r.name, !0);
				break;
			case "select":
				Q("invalid", t);
				break;
			case "textarea": Q("invalid", t), ln(t, r.value, r.defaultValue, r.children);
		}
		n = r.children, typeof n != "string" && typeof n != "number" && typeof n != "bigint" || t.textContent === "" + n || !0 === r.suppressHydrationWarning || ep(t.textContent, n) ? (r.popover != null && (Q("beforetoggle", t), Q("toggle", t)), r.onScroll != null && Q("scroll", t), r.onScrollEnd != null && Q("scrollend", t), r.onClick != null && (t.onclick = vn), t = !0) : t = !1, t || sa(e, !0);
	}
	function la(e) {
		for (ra = e.return; ra;) switch (ra.tag) {
			case 5:
			case 31:
			case 13:
				aa = !1;
				return;
			case 27:
			case 3:
				aa = !0;
				return;
			default: ra = ra.return;
		}
	}
	function ua(e) {
		if (e !== ra) return !1;
		if (!V) return la(e), V = !0, !1;
		var t = e.tag, n;
		if ((n = t !== 3 && t !== 27) && ((n = t === 5) && (n = e.type, n = n === "form" || n === "button" || pp(e.type, e.memoizedProps)), n = !n), n && B && sa(e), la(e), t === 13) {
			if (e = e.memoizedState, e = e === null ? null : e.dehydrated, !e) throw Error(s(317));
			B = dm(e);
		} else if (t === 31) {
			if (e = e.memoizedState, e = e === null ? null : e.dehydrated, !e) throw Error(s(317));
			B = dm(e);
		} else t === 27 ? (t = B, Sp(e.type) ? (e = um, um = null, B = e) : B = t) : B = ra ? lm(e.stateNode.nextSibling) : null;
		return !0;
	}
	function da() {
		B = ra = null, V = !1;
	}
	function fa() {
		var e = ia;
		return e !== null && (fd === null ? fd = e : fd.push.apply(fd, e), ia = null), e;
	}
	function pa(e) {
		ia === null ? ia = [e] : ia.push(e);
	}
	var ma = j(null), ha = null, ga = null;
	function _a(e, t, n) {
		N(ma, t._currentValue), t._currentValue = n;
	}
	function va(e) {
		e._currentValue = ma.current, M(ma);
	}
	function ya(e, t, n) {
		for (; e !== null;) {
			var r = e.alternate;
			if ((e.childLanes & t) === t ? r !== null && (r.childLanes & t) !== t && (r.childLanes |= t) : (e.childLanes |= t, r !== null && (r.childLanes |= t)), e === n) break;
			e = e.return;
		}
	}
	function ba(e, t, n, r) {
		var i = e.child;
		for (i !== null && (i.return = e); i !== null;) {
			var a = i.dependencies;
			if (a !== null) {
				var o = i.child;
				a = a.firstContext;
				a: for (; a !== null;) {
					var c = a;
					a = i;
					for (var l = 0; l < t.length; l++) if (c.context === t[l]) {
						a.lanes |= n, c = a.alternate, c !== null && (c.lanes |= n), ya(a.return, n, e), r || (o = null);
						break a;
					}
					a = c.next;
				}
			} else if (i.tag === 18) {
				if (o = i.return, o === null) throw Error(s(341));
				o.lanes |= n, a = o.alternate, a !== null && (a.lanes |= n), ya(o, n, e), o = null;
			} else i.tag === 13 && i.memoizedState !== null && i.memoizedState.dehydrated === null ? (i.lanes |= n, o = i.alternate, o !== null && (o.lanes |= n), ya(i.return, n, e), o = i.child, o = o === null ? null : o.sibling) : o = i.child;
			if (o !== null) o.return = i;
			else for (o = i; o !== null;) {
				if (o === e) {
					o = null;
					break;
				}
				if (i = o.sibling, i !== null) {
					i.return = o.return, o = i;
					break;
				}
				o = o.return;
			}
			i = o;
		}
	}
	function xa(e, t, n, r) {
		e = null;
		for (var i = t, a = !1; i !== null;) {
			if (!a) {
				if (i.flags & 524288) a = !0;
				else if (i.flags & 262144) break;
			}
			if (i.tag === 10) {
				var o = i.alternate;
				if (o === null) throw Error(s(387));
				if (o = o.memoizedProps, o !== null) {
					var c = i.type;
					Vr(i.pendingProps.value, o.value) || (e === null ? e = [c] : e.push(c));
				}
			} else if (i === Oe.current) {
				if (o = i.alternate, o === null) throw Error(s(387));
				o.memoizedState.memoizedState !== i.memoizedState.memoizedState && (e === null ? e = [sh] : e.push(sh));
			}
			i = i.return;
		}
		return e !== null && ba(t, e, n, r), t.flags |= 262144, e !== null;
	}
	function Sa(e) {
		for (e = e.firstContext; e !== null;) {
			if (!Vr(e.context._currentValue, e.memoizedValue)) return !0;
			e = e.next;
		}
		return !1;
	}
	function Ca(e) {
		ha = e, ga = null, e = e.dependencies, e !== null && (e.firstContext = null);
	}
	function wa(e) {
		return Ea(ha, e);
	}
	function Ta(e, t) {
		return ha === null && Ca(e), Ea(e, t);
	}
	function Ea(e, t) {
		var n = t._currentValue;
		if (t = {
			context: t,
			memoizedValue: n,
			next: null
		}, ga === null) {
			if (e === null) throw Error(s(308));
			ga = t, e.dependencies = {
				lanes: 0,
				firstContext: t
			}, e.flags |= 524288;
		} else ga = ga.next = t;
		return n;
	}
	var Da = typeof AbortController < "u" ? AbortController : function() {
		var e = [], t = this.signal = {
			aborted: !1,
			addEventListener: function(t, n) {
				e.push(n);
			}
		};
		this.abort = function() {
			t.aborted = !0, e.forEach(function(e) {
				return e();
			});
		};
	}, Oa = t.unstable_scheduleCallback, ka = t.unstable_NormalPriority, Aa = {
		$$typeof: se,
		Consumer: null,
		Provider: null,
		_currentValue: null,
		_currentValue2: null,
		_threadCount: 0
	};
	function ja() {
		return {
			controller: new Da(),
			data: /* @__PURE__ */ new Map(),
			refCount: 0
		};
	}
	function Ma(e) {
		e.refCount--, e.refCount === 0 && Oa(ka, function() {
			e.controller.abort();
		});
	}
	function Na(e, t) {
		if (e.pendingLanes & 4194048) {
			var n = e.transitionTypes;
			for (n === null && (n = e.transitionTypes = []), e = 0; e < t.length; e++) {
				var r = t[e];
				n.indexOf(r) === -1 && n.push(r);
			}
		}
	}
	var Pa = null;
	function Fa(e) {
		var t = e.transitionTypes;
		return e.transitionTypes = null, t;
	}
	var Ia = null, La = 0, Ra = 0, za = null;
	function Ba(e, t) {
		if (Ia === null) {
			var n = Ia = [];
			La = 0, Ra = Pf(), za = {
				status: "pending",
				value: void 0,
				then: function(e) {
					n.push(e);
				}
			};
		}
		return La++, t.then(Va, Va), t;
	}
	function Va() {
		if (--La === 0 && (Pa = null, Ia !== null)) {
			za !== null && (za.status = "fulfilled");
			var e = Ia;
			Ia = null, Ra = 0, za = null;
			for (var t = 0; t < e.length; t++) (0, e[t])();
		}
	}
	function Ha(e, t) {
		var n = [], r = {
			status: "pending",
			value: null,
			reason: null,
			then: function(e) {
				n.push(e);
			}
		};
		return e.then(function() {
			r.status = "fulfilled", r.value = t;
			for (var e = 0; e < n.length; e++) (0, n[e])(t);
		}, function(e) {
			for (r.status = "rejected", r.reason = e, e = 0; e < n.length; e++) (0, n[e])(void 0);
		}), r;
	}
	var Ua = k.S;
	k.S = function(e, t) {
		if (hd = P(), typeof t == "object" && t && typeof t.then == "function" && Ba(e, t), Pa !== null) for (var n = bf; n !== null;) Na(n, Pa), n = n.next;
		if (n = e.types, n !== null) {
			for (var r = bf; r !== null;) Na(r, n), r = r.next;
			if (Ra !== 0) {
				r = Pa, r === null && (r = Pa = []);
				for (var i = 0; i < n.length; i++) {
					var a = n[i];
					r.indexOf(a) === -1 && r.push(a);
				}
			}
		}
		Ua !== null && Ua(e, t);
	};
	var Wa = j(null);
	function Ga() {
		var e = Wa.current;
		return e === null ? q.pooledCache : e;
	}
	function Ka(e, t) {
		t === null ? N(Wa, Wa.current) : N(Wa, t.pool);
	}
	function qa() {
		var e = Ga();
		return e === null ? null : {
			parent: Aa._currentValue,
			pool: e
		};
	}
	var Ja = Error(s(460)), Ya = Error(s(474)), Xa = Error(s(542)), Za = { then: function() {} };
	function Qa(e) {
		return e = e.status, e === "fulfilled" || e === "rejected";
	}
	function $a(e, t, n) {
		switch (n = e[n], n === void 0 ? e.push(t) : n !== t && (t.then(vn, vn), t = n), t.status) {
			case "fulfilled": return t.value;
			case "rejected": throw e = t.reason, ro(e), e === void 0 && !("reason" in t) ? Error(s(600)) : e;
			default:
				if (typeof t.status == "string") t.then(vn, vn);
				else {
					if (e = q, e !== null && 100 < e.shellSuspendCounter) throw Error(s(482));
					e = t, e.status = "pending", e.then(function(e) {
						if (t.status === "pending") {
							var n = t;
							n.status = "fulfilled", n.value = e;
						}
					}, function(e) {
						if (t.status === "pending") {
							var n = t;
							n.status = "rejected", n.reason = e;
						}
					});
				}
				switch (t.status) {
					case "fulfilled": return t.value;
					case "rejected": throw e = t.reason, ro(e), e;
				}
				throw to = t, Ja;
		}
	}
	function eo(e) {
		try {
			var t = e._init;
			return t(e._payload);
		} catch (e) {
			throw typeof e == "object" && e && typeof e.then == "function" ? (to = e, Ja) : e;
		}
	}
	var to = null;
	function no() {
		if (to === null) throw Error(s(459));
		var e = to;
		return to = null, e;
	}
	function ro(e) {
		if (e === Ja || e === Xa) throw Error(s(483));
	}
	var io = null, ao = 0;
	function oo(e) {
		var t = ao;
		return ao += 1, io === null && (io = []), $a(io, e, t);
	}
	function so(e, t) {
		t = t.props.ref, e.ref = t === void 0 ? null : t;
	}
	function co(e, t) {
		throw t.$$typeof === re ? Error(s(525)) : (e = Object.prototype.toString.call(t), Error(s(31, e === "[object Object]" ? "object with keys {" + Object.keys(t).join(", ") + "}" : e)));
	}
	function lo(e) {
		function t(t, n) {
			if (e) {
				var r = t.deletions;
				r === null ? (t.deletions = [n], t.flags |= 16) : r.push(n);
			}
		}
		function n(n, r) {
			if (!e) return null;
			for (; r !== null;) t(n, r), r = r.sibling;
			return null;
		}
		function r(e) {
			for (var t = /* @__PURE__ */ new Map(); e !== null;) e.key === null ? t.set(e.index, e) : t.set(e.key, e), e = e.sibling;
			return t;
		}
		function i(e, t) {
			return e = Pi(e, t), e.index = 0, e.sibling = null, e;
		}
		function a(t, n, r) {
			return t.index = r, e ? (r = t.alternate, r === null ? (t.flags |= 134217730, n) : (r = r.index, r < n ? (t.flags |= 2, n) : r)) : (t.flags |= 1048576, n);
		}
		function o(t) {
			return e && t.alternate === null && (t.flags |= 134217730), t;
		}
		function c(e, t, n, r) {
			return t === null || t.tag !== 6 ? (t = Ri(n, e.mode, r), t.return = e, t) : (t = i(t, n), t.return = e, t);
		}
		function l(e, t, n, r) {
			var a = n.type;
			return a === D ? (e = d(e, t, n.props.children, r, n.key), so(e, n), e) : t !== null && (t.elementType === a || typeof a == "object" && a && a.$$typeof === de && eo(a) === t.type) ? (t = i(t, n.props), so(t, n), t.return = e, t) : (t = Ii(n.type, n.key, n.props, null, e.mode, r), so(t, n), t.return = e, t);
		}
		function u(e, t, n, r) {
			return t === null || t.tag !== 4 || t.stateNode.containerInfo !== n.containerInfo || t.stateNode.implementation !== n.implementation ? (t = Bi(n, e.mode, r), t.return = e, t) : (t = i(t, n.children || []), t.return = e, t);
		}
		function d(e, t, n, r, a) {
			return t === null || t.tag !== 7 ? (t = Li(n, e.mode, r, a), t.return = e, t) : (t = i(t, n), t.return = e, t);
		}
		function f(e, t, n) {
			if (typeof t == "string" && t !== "" || typeof t == "number" || typeof t == "bigint") return t = Ri("" + t, e.mode, n), t.return = e, t;
			if (typeof t == "object" && t) {
				switch (t.$$typeof) {
					case T: return n = Ii(t.type, t.key, t.props, null, e.mode, n), so(n, t), n.return = e, n;
					case E: return t = Bi(t, e.mode, n), t.return = e, t;
					case de: return t = eo(t), f(e, t, n);
				}
				if (xe(t) || ve(t)) return t = Li(t, e.mode, n, null), t.return = e, t;
				if (typeof t.then == "function") return f(e, oo(t), n);
				if (t.$$typeof === se) return f(e, Ta(e, t), n);
				co(e, t);
			}
			return null;
		}
		function p(e, t, n, r) {
			var i = t === null ? null : t.key;
			if (typeof n == "string" && n !== "" || typeof n == "number" || typeof n == "bigint") return i === null ? c(e, t, "" + n, r) : null;
			if (typeof n == "object" && n) {
				switch (n.$$typeof) {
					case T: return n.key === i ? l(e, t, n, r) : null;
					case E: return n.key === i ? u(e, t, n, r) : null;
					case de: return n = eo(n), p(e, t, n, r);
				}
				if (xe(n) || ve(n)) return i === null ? d(e, t, n, r, null) : null;
				if (typeof n.then == "function") return p(e, t, oo(n), r);
				if (n.$$typeof === se) return p(e, t, Ta(e, n), r);
				co(e, n);
			}
			return null;
		}
		function m(e, t, n, r, i) {
			if (typeof r == "string" && r !== "" || typeof r == "number" || typeof r == "bigint") return e = e.get(n) || null, c(t, e, "" + r, i);
			if (typeof r == "object" && r) {
				switch (r.$$typeof) {
					case T: return e = e.get(r.key === null ? n : r.key) || null, l(t, e, r, i);
					case E: return e = e.get(r.key === null ? n : r.key) || null, u(t, e, r, i);
					case de: return r = eo(r), m(e, t, n, r, i);
				}
				if (xe(r) || ve(r)) return e = e.get(n) || null, d(t, e, r, i, null);
				if (typeof r.then == "function") return m(e, t, n, oo(r), i);
				if (r.$$typeof === se) return m(e, t, n, Ta(t, r), i);
				co(t, r);
			}
			return null;
		}
		function h(i, o, s, c) {
			for (var l = null, u = null, d = o, h = o = 0, g = null; d !== null && h < s.length; h++) {
				d.index > h ? (g = d, d = null) : g = d.sibling;
				var _ = p(i, d, s[h], c);
				if (_ === null) {
					d === null && (d = g);
					break;
				}
				e && d && _.alternate === null && t(i, d), o = a(_, o, h), u === null ? l = _ : u.sibling = _, u = _, d = g;
			}
			if (h === s.length) return n(i, d), V && Qi(i, h), l;
			if (d === null) {
				for (; h < s.length; h++) d = f(i, s[h], c), d !== null && (o = a(d, o, h), u === null ? l = d : u.sibling = d, u = d);
				return V && Qi(i, h), l;
			}
			for (d = r(d); h < s.length; h++) g = m(d, i, h, s[h], c), g !== null && (e && (_ = g.alternate, _ !== null && d.delete(_.key === null ? h : _.key)), o = a(g, o, h), u === null ? l = g : u.sibling = g, u = g);
			return e && d.forEach(function(e) {
				return t(i, e);
			}), V && Qi(i, h), l;
		}
		function g(i, o, c, l) {
			if (c == null) throw Error(s(151));
			for (var u = null, d = null, h = o, g = o = 0, _ = null, v = c.next(); h !== null && !v.done; g++, v = c.next()) {
				h.index > g ? (_ = h, h = null) : _ = h.sibling;
				var y = p(i, h, v.value, l);
				if (y === null) {
					h === null && (h = _);
					break;
				}
				e && h && y.alternate === null && t(i, h), o = a(y, o, g), d === null ? u = y : d.sibling = y, d = y, h = _;
			}
			if (v.done) return n(i, h), V && Qi(i, g), u;
			if (h === null) {
				for (; !v.done; g++, v = c.next()) v = f(i, v.value, l), v !== null && (o = a(v, o, g), d === null ? u = v : d.sibling = v, d = v);
				return V && Qi(i, g), u;
			}
			for (h = r(h); !v.done; g++, v = c.next()) v = m(h, i, g, v.value, l), v !== null && (e && (_ = v.alternate, _ !== null && h.delete(_.key === null ? g : _.key)), o = a(v, o, g), d === null ? u = v : d.sibling = v, d = v);
			return e && h.forEach(function(e) {
				return t(i, e);
			}), V && Qi(i, g), u;
		}
		function _(e, r, a, c) {
			if (typeof a == "object" && a && a.type === D && a.key === null && a.props.ref === void 0 && (a = a.props.children), typeof a == "object" && a) {
				switch (a.$$typeof) {
					case T:
						a: {
							for (var l = a.key; r !== null;) {
								if (r.key === l) {
									if (l = a.type, l === D) {
										if (r.tag === 7) {
											n(e, r.sibling), c = i(r, a.props.children), so(c, a), c.return = e, e = c;
											break a;
										}
									} else if (r.elementType === l || typeof l == "object" && l && l.$$typeof === de && eo(l) === r.type) {
										n(e, r.sibling), c = i(r, a.props), so(c, a), c.return = e, e = c;
										break a;
									}
									n(e, r);
									break;
								}
								t(e, r), r = r.sibling;
							}
							a.type === D ? (c = Li(a.props.children, e.mode, c, a.key), so(c, a), c.return = e, e = c) : (c = Ii(a.type, a.key, a.props, null, e.mode, c), so(c, a), c.return = e, e = c);
						}
						return o(e);
					case E:
						a: {
							for (l = a.key; r !== null;) {
								if (r.key === l) {
									if (r.tag === 4 && r.stateNode.containerInfo === a.containerInfo && r.stateNode.implementation === a.implementation) {
										n(e, r.sibling), c = i(r, a.children || []), c.return = e, e = c;
										break a;
									}
									n(e, r);
									break;
								}
								t(e, r), r = r.sibling;
							}
							c = Bi(a, e.mode, c), c.return = e, e = c;
						}
						return o(e);
					case de: return a = eo(a), _(e, r, a, c);
				}
				if (xe(a)) return h(e, r, a, c);
				if (ve(a)) {
					if (l = ve(a), typeof l != "function") throw Error(s(150));
					return a = l.call(a), g(e, r, a, c);
				}
				if (typeof a.then == "function") return _(e, r, oo(a), c);
				if (a.$$typeof === se) return _(e, r, Ta(e, a), c);
				co(e, a);
			}
			return typeof a == "string" && a !== "" || typeof a == "number" || typeof a == "bigint" ? (a = "" + a, r !== null && r.tag === 6 ? (n(e, r.sibling), c = i(r, a), c.return = e, e = c) : (n(e, r), c = Ri(a, e.mode, c), c.return = e, e = c), o(e)) : n(e, r);
		}
		return function(e, t, n, r) {
			try {
				ao = 0;
				var i = _(e, t, n, r);
				return io = null, i;
			} catch (t) {
				if (t === Ja || t === Xa) throw t;
				var a = Mi(29, t, null, e.mode);
				return a.lanes = r, a.return = e, a;
			}
		};
	}
	var uo = lo(!0), fo = lo(!1), po = !1;
	function mo(e) {
		e.updateQueue = {
			baseState: e.memoizedState,
			firstBaseUpdate: null,
			lastBaseUpdate: null,
			shared: {
				pending: null,
				lanes: 0,
				hiddenCallbacks: null
			},
			callbacks: null
		};
	}
	function ho(e, t) {
		e = e.updateQueue, t.updateQueue === e && (t.updateQueue = {
			baseState: e.baseState,
			firstBaseUpdate: e.firstBaseUpdate,
			lastBaseUpdate: e.lastBaseUpdate,
			shared: e.shared,
			callbacks: null
		});
	}
	function go(e) {
		return {
			lane: e,
			tag: 0,
			payload: null,
			callback: null,
			next: null
		};
	}
	function _o(e, t, n) {
		var r = e.updateQueue;
		if (r === null) return null;
		if (r = r.shared, K & 2) {
			var i = r.pending;
			return i === null ? t.next = t : (t.next = i.next, i.next = t), r.pending = t, t = ki(e), Oi(e, null, n), t;
		}
		return Ti(e, r, t, n), ki(e);
	}
	function vo(e, t, n) {
		if (t = t.updateQueue, t !== null && (t = t.shared, n & 4194048)) {
			var r = t.lanes;
			r &= e.pendingLanes, n |= r, t.lanes = n, yt(e, n);
		}
	}
	function yo(e, t) {
		var n = e.updateQueue, r = e.alternate;
		if (r !== null && (r = r.updateQueue, n === r)) {
			var i = null, a = null;
			if (n = n.firstBaseUpdate, n !== null) {
				do {
					var o = {
						lane: n.lane,
						tag: n.tag,
						payload: n.payload,
						callback: null,
						next: null
					};
					a === null ? i = a = o : a = a.next = o, n = n.next;
				} while (n !== null);
				a === null ? i = a = t : a = a.next = t;
			} else i = a = t;
			n = {
				baseState: r.baseState,
				firstBaseUpdate: i,
				lastBaseUpdate: a,
				shared: r.shared,
				callbacks: r.callbacks
			}, e.updateQueue = n;
		} else e = n.lastBaseUpdate, e === null ? n.firstBaseUpdate = t : e.next = t, n.lastBaseUpdate = t;
	}
	var bo = !1;
	function xo() {
		if (bo) {
			var e = za;
			if (e !== null) throw e;
		}
	}
	function So(e, t, n, r) {
		bo = !1;
		var i = e.updateQueue;
		po = !1;
		var a = i.firstBaseUpdate, o = i.lastBaseUpdate, s = i.shared.pending;
		if (s !== null) {
			i.shared.pending = null;
			var c = s, l = c.next;
			c.next = null, o === null ? a = l : o.next = l, o = c;
			var u = e.alternate;
			u !== null && (u = u.updateQueue, s = u.lastBaseUpdate, s !== o && (s === null ? u.firstBaseUpdate = l : s.next = l, u.lastBaseUpdate = c));
		}
		if (a !== null) {
			var d = i.baseState;
			o = 0, u = l = c = null, s = a;
			do {
				var f = s.lane & -536870913, p = f !== s.lane;
				if (p ? (Y & f) === f : (r & f) === f) {
					f !== 0 && f === Ra && (bo = !0), u !== null && (u = u.next = {
						lane: 0,
						tag: s.tag,
						payload: s.payload,
						callback: null,
						next: null
					});
					a: {
						var m = e, h = s;
						f = t;
						var g = n;
						switch (h.tag) {
							case 1:
								if (m = h.payload, typeof m == "function") {
									d = m.call(g, d, f);
									break a;
								}
								d = m;
								break a;
							case 3: m.flags = m.flags & -65537 | 128;
							case 0:
								if (m = h.payload, f = typeof m == "function" ? m.call(g, d, f) : m, f == null) break a;
								d = w({}, d, f);
								break a;
							case 2: po = !0;
						}
					}
					f = s.callback, f !== null && (e.flags |= 64, p && (e.flags |= 8192), p = i.callbacks, p === null ? i.callbacks = [f] : p.push(f));
				} else p = {
					lane: f,
					tag: s.tag,
					payload: s.payload,
					callback: s.callback,
					next: null
				}, u === null ? (l = u = p, c = d) : u = u.next = p, o |= f;
				if (s = s.next, s === null) {
					if (s = i.shared.pending, s === null) break;
					p = s, s = p.next, p.next = null, i.lastBaseUpdate = p, i.shared.pending = null;
				}
			} while (1);
			u === null && (c = d), i.baseState = c, i.firstBaseUpdate = l, i.lastBaseUpdate = u, a === null && (i.shared.lanes = 0), od |= o, e.lanes = o, e.memoizedState = d;
		}
	}
	function Co(e, t) {
		if (typeof e != "function") throw Error(s(191, e));
		e.call(t);
	}
	function wo(e, t) {
		var n = e.callbacks;
		if (n !== null) for (e.callbacks = null, e = 0; e < n.length; e++) Co(n[e], t);
	}
	var To = j(null), Eo = j(0);
	function Do(e, t) {
		e = id, N(Eo, e), N(To, t), id = e | t.baseLanes;
	}
	function Oo() {
		N(Eo, id), N(To, To.current);
	}
	function ko() {
		id = Eo.current, M(To), M(Eo);
	}
	var Ao = j(null), jo = null;
	function Mo(e) {
		var t = e.alternate;
		N(Lo, Lo.current & 1), N(Ao, e), jo === null && (t === null || To.current !== null || t.memoizedState !== null) && (jo = e);
	}
	function No(e) {
		N(Lo, Lo.current), N(Ao, e), jo === null && (jo = e);
	}
	function Po(e) {
		e.tag === 22 ? (N(Lo, Lo.current), N(Ao, e), jo === null && (jo = e)) : Fo();
	}
	function Fo() {
		N(Lo, Lo.current), N(Ao, Ao.current);
	}
	function Io(e) {
		M(Ao), jo === e && (jo = null), M(Lo);
	}
	var Lo = j(0);
	function Ro(e, t) {
		N(Ao, Ao.current), N(Lo, t);
	}
	function zo(e) {
		M(Lo), M(Ao), jo === e && (jo = null);
	}
	function Bo(e) {
		for (var t = e; t !== null;) {
			if (t.tag === 13) {
				var n = t.memoizedState;
				if (n !== null && (n = n.dehydrated, n === null || om(n) || sm(n))) return t;
			} else if (t.tag === 19 && t.memoizedProps.revealOrder !== "independent") {
				if (t.flags & 128) return t;
			} else if (t.child !== null) {
				t.child.return = t, t = t.child;
				continue;
			}
			if (t === e) break;
			for (; t.sibling === null;) {
				if (t.return === null || t.return === e) return null;
				t = t.return;
			}
			t.sibling.return = t.return, t = t.sibling;
		}
		return null;
	}
	var Vo = 0, H = null, U = null, Ho = null, Uo = !1, Wo = !1, Go = !1, Ko = 0, qo = 0, Jo = null, Yo = 0;
	function Xo() {
		throw Error(s(321));
	}
	function Zo(e, t) {
		if (t === null) return !1;
		for (var n = 0; n < t.length && n < e.length; n++) if (!Vr(e[n], t[n])) return !1;
		return !0;
	}
	function Qo(e, t, n, r, i, a) {
		return Vo = a, H = t, t.memoizedState = null, t.updateQueue = null, t.lanes = 0, k.H = e === null || e.memoizedState === null ? hc : gc, Go = !1, a = n(r, i), Go = !1, Wo && (a = es(t, n, r, i)), $o(e), a;
	}
	function $o(e) {
		k.H = mc;
		var t = U !== null && U.next !== null;
		if (Vo = 0, Ho = U = H = null, Uo = !1, qo = 0, Jo = null, t) throw Error(s(300));
		e === null || Nc || (e = e.dependencies, e !== null && Sa(e) && (Nc = !0));
	}
	function es(e, t, n, r) {
		H = e;
		var i = 0;
		do {
			if (Wo && (Jo = null), qo = 0, Wo = !1, 25 <= i) throw Error(s(301));
			if (i += 1, Ho = U = null, e.updateQueue != null) {
				var a = e.updateQueue;
				a.lastEffect = null, a.events = null, a.stores = null, a.memoCache != null && (a.memoCache.index = 0);
			}
			k.H = _c, a = t(n, r);
		} while (Wo);
		return a;
	}
	function ts() {
		var e = k.H, t = e.useState()[0];
		return t = typeof t.then == "function" ? cs(t) : t, e = e.useState()[0], (U === null ? null : U.memoizedState) !== e && (H.flags |= 1024), t;
	}
	function ns() {
		var e = Ko !== 0;
		return Ko = 0, e;
	}
	function rs(e, t, n) {
		t.updateQueue = e.updateQueue, t.flags &= -2053, e.lanes &= ~n;
	}
	function is(e) {
		if (Uo) {
			for (e = e.memoizedState; e !== null;) {
				var t = e.queue;
				t !== null && (t.pending = null), e = e.next;
			}
			Uo = !1;
		}
		Vo = 0, Ho = U = H = null, Wo = !1, qo = Ko = 0, Jo = null;
	}
	function as() {
		var e = {
			memoizedState: null,
			baseState: null,
			baseQueue: null,
			queue: null,
			next: null
		};
		return Ho === null ? H.memoizedState = Ho = e : Ho = Ho.next = e, Ho;
	}
	function os() {
		if (U === null) {
			var e = H.alternate;
			e = e === null ? null : e.memoizedState;
		} else e = U.next;
		var t = Ho === null ? H.memoizedState : Ho.next;
		if (t !== null) Ho = t, U = e;
		else {
			if (e === null) throw H.alternate === null ? Error(s(467)) : Error(s(310));
			U = e, e = {
				memoizedState: U.memoizedState,
				baseState: U.baseState,
				baseQueue: U.baseQueue,
				queue: U.queue,
				next: null
			}, Ho === null ? H.memoizedState = Ho = e : Ho = Ho.next = e;
		}
		return Ho;
	}
	function ss() {
		return {
			lastEffect: null,
			events: null,
			stores: null,
			memoCache: null
		};
	}
	function cs(e) {
		var t = qo;
		return qo += 1, Jo === null && (Jo = []), e = $a(Jo, e, t), t = H, (Ho === null ? t.memoizedState : Ho.next) === null && (t = t.alternate, k.H = t === null || t.memoizedState === null ? hc : gc), e;
	}
	function ls(e) {
		if (typeof e == "object" && e) {
			if (typeof e.then == "function") return cs(e);
			if (e.$$typeof === ge) return;
			if (e.$$typeof === se) return wa(e);
		}
		throw Error(s(438, String(e)));
	}
	function us(e) {
		var t = null, n = H.updateQueue;
		if (n !== null && (t = n.memoCache), t == null) {
			var r = H.alternate;
			r !== null && (r = r.updateQueue, r !== null && (r = r.memoCache, r != null && (t = {
				data: r.data.map(function(e) {
					return e.slice();
				}),
				index: 0
			})));
		}
		if (t ??= {
			data: [],
			index: 0
		}, n === null && (n = ss(), H.updateQueue = n), n.memoCache = t, n = t.data[t.index], n === void 0) for (n = t.data[t.index] = Array(e), r = 0; r < e; r++) n[r] = me;
		return t.index++, n;
	}
	function ds(e, t) {
		return typeof t == "function" ? t(e) : t;
	}
	function fs(e) {
		return ps(os(), U, e);
	}
	function ps(e, t, n) {
		var r = e.queue;
		if (r === null) throw Error(s(311));
		r.lastRenderedReducer = n;
		var i = e.baseQueue, a = r.pending;
		if (a !== null) {
			if (i !== null) {
				var o = i.next;
				i.next = a.next, a.next = o;
			}
			t.baseQueue = i = a, r.pending = null;
		}
		if (a = e.baseState, i === null) e.memoizedState = a;
		else {
			t = i.next;
			var c = o = null, l = null, u = t, d = !1;
			do {
				var f = u.lane & -536870913;
				if (f === u.lane ? (Vo & f) === f : (Y & f) === f) {
					var p = u.revertLane;
					if (p === 0) l !== null && (l = l.next = {
						lane: 0,
						revertLane: 0,
						gesture: null,
						action: u.action,
						hasEagerState: u.hasEagerState,
						eagerState: u.eagerState,
						next: null
					}), f === Ra && (d = !0);
					else if ((Vo & p) === p) {
						u = u.next, p === Ra && (d = !0);
						continue;
					} else f = {
						lane: 0,
						revertLane: u.revertLane,
						gesture: null,
						action: u.action,
						hasEagerState: u.hasEagerState,
						eagerState: u.eagerState,
						next: null
					}, l === null ? (c = l = f, o = a) : l = l.next = f, H.lanes |= p, od |= p;
					f = u.action, Go && n(a, f), a = u.hasEagerState ? u.eagerState : n(a, f);
				} else p = {
					lane: f,
					revertLane: u.revertLane,
					gesture: u.gesture,
					action: u.action,
					hasEagerState: u.hasEagerState,
					eagerState: u.eagerState,
					next: null
				}, l === null ? (c = l = p, o = a) : l = l.next = p, H.lanes |= f, od |= f;
				u = u.next;
			} while (u !== null && u !== t);
			if (l === null ? o = a : l.next = c, !Vr(a, e.memoizedState) && (Nc = !0, d && (n = za, n !== null))) throw n;
			e.memoizedState = a, e.baseState = o, e.baseQueue = l, r.lastRenderedState = a;
		}
		return i === null && (r.lanes = 0), [e.memoizedState, r.dispatch];
	}
	function ms(e) {
		var t = os(), n = t.queue;
		if (n === null) throw Error(s(311));
		n.lastRenderedReducer = e;
		var r = n.dispatch, i = n.pending, a = t.memoizedState;
		if (i !== null) {
			n.pending = null;
			var o = i = i.next;
			do
				a = e(a, o.action), o = o.next;
			while (o !== i);
			Vr(a, t.memoizedState) || (Nc = !0), t.memoizedState = a, t.baseQueue === null && (t.baseState = a), n.lastRenderedState = a;
		}
		return [a, r];
	}
	function hs(e, t, n) {
		var r = H, i = os(), a = V;
		if (a) {
			if (n === void 0) throw Error(s(407));
			n = n();
		} else n = t();
		var o = !Vr((U || i).memoizedState, n);
		if (o && (i.memoizedState = n, Nc = !0), i = i.queue, Bs(vs.bind(null, r, i, e), [e]), e = i.getSnapshot !== t || o || Ho !== null && !!(Ho.memoizedState.tag & 1), Fs(e ? 9 : 8, { destroy: void 0 }, _s.bind(null, r, i, n, t), null), e) {
			if (r.flags |= 2048, q === null) throw Error(s(349));
			a || Vo & 127 || gs(r, t, n);
		}
		return n;
	}
	function gs(e, t, n) {
		e.flags |= 16384, e = {
			getSnapshot: t,
			value: n
		}, t = H.updateQueue, t === null ? (t = ss(), H.updateQueue = t, t.stores = [e]) : (n = t.stores, n === null ? t.stores = [e] : n.push(e));
	}
	function _s(e, t, n, r) {
		t.value = n, t.getSnapshot = r, ys(t) && bs(e);
	}
	function vs(e, t, n) {
		return n(function() {
			ys(t) && bs(e);
		});
	}
	function ys(e) {
		var t = e.getSnapshot;
		e = e.value;
		try {
			var n = t();
			return !Vr(e, n);
		} catch {
			return !0;
		}
	}
	function bs(e) {
		var t = Di(e, 2);
		t !== null && Pd(t, e, 2);
	}
	function xs(e) {
		var t = as();
		if (typeof e == "function") {
			var n = e;
			if (e = n(), Go) {
				tt(!0);
				try {
					n();
				} finally {
					tt(!1);
				}
			}
		}
		return t.memoizedState = t.baseState = e, t.queue = {
			pending: null,
			lanes: 0,
			dispatch: null,
			lastRenderedReducer: ds,
			lastRenderedState: e
		}, t;
	}
	function Ss(e, t, n, r) {
		return e.baseState = n, ps(e, U, typeof r == "function" ? r : ds);
	}
	function Cs(e, t, n, r, i) {
		if (dc(e)) throw Error(s(485));
		if (e = t.action, e !== null) {
			var a = {
				payload: i,
				action: e,
				next: null,
				isTransition: !0,
				status: "pending",
				value: null,
				reason: null,
				listeners: [],
				then: function(e) {
					a.listeners.push(e);
				}
			};
			k.T === null ? a.isTransition = !1 : n(!0), r(a), n = t.pending, n === null ? (a.next = t.pending = a, ws(t, a)) : (a.next = n.next, t.pending = n.next = a);
		}
	}
	function ws(e, t) {
		var n = t.action, r = t.payload, i = e.state;
		if (t.isTransition) {
			var a = k.T, o = {};
			o.types = a === null ? null : a.types, k.T = o;
			try {
				var s = n(i, r), c = k.S;
				c !== null && c(o, s), Ts(e, t, s);
			} catch (n) {
				Ds(e, t, n);
			} finally {
				a !== null && o.types !== null && (a.types = o.types), k.T = a;
			}
		} else try {
			a = n(i, r), Ts(e, t, a);
		} catch (n) {
			Ds(e, t, n);
		}
	}
	function Ts(e, t, n) {
		typeof n == "object" && n && typeof n.then == "function" ? n.then(function(n) {
			Es(e, t, n);
		}, function(n) {
			return Ds(e, t, n);
		}) : Es(e, t, n);
	}
	function Es(e, t, n) {
		t.status = "fulfilled", t.value = n, Os(t), e.state = n, t = e.pending, t !== null && (n = t.next, n === t ? e.pending = null : (n = n.next, t.next = n, ws(e, n)));
	}
	function Ds(e, t, n) {
		var r = e.pending;
		if (e.pending = null, r !== null) {
			r = r.next;
			do
				t.status = "rejected", t.reason = n, Os(t), t = t.next;
			while (t !== r);
		}
		e.action = null;
	}
	function Os(e) {
		e = e.listeners;
		for (var t = 0; t < e.length; t++) (0, e[t])();
	}
	function ks(e, t) {
		return t;
	}
	function As(e, t) {
		if (V) {
			var n = q.formState;
			if (n !== null) {
				a: {
					var r = H;
					if (V) {
						if (B) {
							b: {
								for (var i = B, a = aa; i.nodeType !== 8;) if (!a || (i = lm(i.nextSibling), i === null)) {
									i = null;
									break b;
								}
								a = i.data, i = a === "F!" || a === "F" ? i : null;
							}
							if (i) {
								B = lm(i.nextSibling), r = i.data === "F!";
								break a;
							}
						}
						sa(r);
					}
					r = !1;
				}
				r && (t = n[0]);
			}
		}
		return n = as(), n.memoizedState = n.baseState = t, r = {
			pending: null,
			lanes: 0,
			dispatch: null,
			lastRenderedReducer: ks,
			lastRenderedState: t
		}, n.queue = r, n = cc.bind(null, H, r), r.dispatch = n, r = xs(!1), a = uc.bind(null, H, !1, r.queue), r = as(), i = {
			state: t,
			dispatch: null,
			action: e,
			pending: null
		}, r.queue = i, n = Cs.bind(null, H, i, a, n), i.dispatch = n, r.memoizedState = e, [
			t,
			n,
			!1
		];
	}
	function js(e) {
		return Ms(os(), U, e);
	}
	function Ms(e, t, n) {
		if (t = ps(e, t, ks)[0], e = fs(ds)[0], typeof t == "object" && t && typeof t.then == "function") try {
			var r = cs(t);
		} catch (e) {
			throw e === Ja ? Xa : e;
		}
		else r = t;
		t = os();
		var i = t.queue, a = i.dispatch;
		return n !== t.memoizedState && (H.flags |= 2048, Fs(9, { destroy: void 0 }, Ns.bind(null, i, n), null)), [
			r,
			a,
			e
		];
	}
	function Ns(e, t) {
		e.action = t;
	}
	function Ps(e) {
		var t = os(), n = U;
		if (n !== null) return Ms(t, n, e);
		os(), t = t.memoizedState, n = os();
		var r = n.queue.dispatch;
		return n.memoizedState = e, [
			t,
			r,
			!1
		];
	}
	function Fs(e, t, n, r) {
		return e = {
			tag: e,
			create: n,
			deps: r,
			inst: t,
			next: null
		}, t = H.updateQueue, t === null && (t = ss(), H.updateQueue = t), n = t.lastEffect, n === null ? t.lastEffect = e.next = e : (r = n.next, n.next = e, e.next = r, t.lastEffect = e), e;
	}
	function Is() {
		return os().memoizedState;
	}
	function Ls(e, t, n, r) {
		var i = as();
		H.flags |= e, i.memoizedState = Fs(1 | t, { destroy: void 0 }, n, r === void 0 ? null : r);
	}
	function Rs(e, t, n, r) {
		var i = os();
		r = r === void 0 ? null : r;
		var a = i.memoizedState.inst;
		U !== null && r !== null && Zo(r, U.memoizedState.deps) ? i.memoizedState = Fs(t, a, n, r) : (H.flags |= e, i.memoizedState = Fs(1 | t, a, n, r));
	}
	function zs(e, t) {
		Ls(8390656, 8, e, t);
	}
	function Bs(e, t) {
		Rs(2048, 8, e, t);
	}
	function Vs(e) {
		H.flags |= 4;
		var t = H.updateQueue;
		if (t === null) t = ss(), H.updateQueue = t, t.events = [e];
		else {
			var n = t.events;
			n === null ? t.events = [e] : n.push(e);
		}
	}
	function Hs(e) {
		var t = os().memoizedState;
		return Vs({
			ref: t,
			nextImpl: e
		}), function() {
			if (K & 2) throw Error(s(440));
			return t.impl.apply(void 0, arguments);
		};
	}
	function Us(e, t) {
		return Rs(4, 2, e, t);
	}
	function Ws(e, t) {
		return Rs(4, 4, e, t);
	}
	function Gs(e, t) {
		if (typeof t == "function") {
			e = e();
			var n = t(e);
			return function() {
				typeof n == "function" ? n() : t(null);
			};
		}
		if (t != null) return e = e(), t.current = e, function() {
			t.current = null;
		};
	}
	function Ks(e, t, n) {
		n = n == null ? null : n.concat([e]), Rs(4, 4, Gs.bind(null, t, e), n);
	}
	function qs() {}
	function Js(e, t) {
		var n = os();
		t = t === void 0 ? null : t;
		var r = n.memoizedState;
		return t !== null && Zo(t, r[1]) ? r[0] : (n.memoizedState = [e, t], e);
	}
	function Ys(e, t) {
		var n = os();
		t = t === void 0 ? null : t;
		var r = n.memoizedState;
		if (t !== null && Zo(t, r[1])) return r[0];
		if (r = e(), Go) {
			tt(!0);
			try {
				e();
			} finally {
				tt(!1);
			}
		}
		return n.memoizedState = [r, t], r;
	}
	function Xs(e, t, n) {
		return n === void 0 || Vo & 1073741824 && !(Y & 261930) ? e.memoizedState = t : (e.memoizedState = n, e = Md(), H.lanes |= e, od |= e, n);
	}
	function Zs(e, t, n, r) {
		return Vr(n, t) ? n : To.current === null ? !(Vo & 106) || Vo & 1073741824 && !(Y & 261930) ? (Nc = !0, e.memoizedState = n) : (e = Md(), H.lanes |= e, od |= e, t) : (e = Xs(e, n, r), Vr(e, t) || (Nc = !0), e);
	}
	function Qs(e, t, n, r, i) {
		var a = A.p;
		A.p = a !== 0 && 8 > a ? a : 8;
		var o = k.T, s = {};
		s.types = o === null ? null : o.types, k.T = s, uc(e, !1, t, n);
		try {
			var c = i(), l = k.S;
			l !== null && l(s, c), typeof c == "object" && c && typeof c.then == "function" ? lc(e, t, Ha(c, r), jd(e)) : lc(e, t, r, jd(e));
		} catch (n) {
			lc(e, t, {
				then: function() {},
				status: "rejected",
				reason: n
			}, jd());
		} finally {
			A.p = a, o !== null && s.types !== null && (o.types = s.types), k.T = o;
		}
	}
	function $s() {}
	function ec(e, t, n, r) {
		if (e.tag !== 5) throw Error(s(476));
		var i = tc(e).queue;
		Qs(e, i, t, Se, n === null ? $s : function() {
			return nc(e), n(r);
		});
	}
	function tc(e) {
		var t = e.memoizedState;
		if (t !== null) return t;
		t = {
			memoizedState: Se,
			baseState: Se,
			baseQueue: null,
			queue: {
				pending: null,
				lanes: 0,
				dispatch: null,
				lastRenderedReducer: ds,
				lastRenderedState: Se
			},
			next: null
		};
		var n = {};
		return t.next = {
			memoizedState: n,
			baseState: n,
			baseQueue: null,
			queue: {
				pending: null,
				lanes: 0,
				dispatch: null,
				lastRenderedReducer: ds,
				lastRenderedState: n
			},
			next: null
		}, e.memoizedState = t, e = e.alternate, e !== null && (e.memoizedState = t), t;
	}
	function nc(e) {
		var t = tc(e);
		t.next === null && (t = e.alternate.memoizedState), lc(e, t.next.queue, {}, jd());
	}
	function rc() {
		return wa(sh);
	}
	function ic() {
		return os().memoizedState;
	}
	function ac() {
		return os().memoizedState;
	}
	function oc(e) {
		for (var t = e.return; t !== null;) {
			switch (t.tag) {
				case 24:
				case 3:
					var n = jd();
					e = go(n);
					var r = _o(t, e, n);
					r !== null && (Pd(r, t, n), vo(r, t, n)), t = { cache: ja() }, e.payload = t;
					return;
			}
			t = t.return;
		}
	}
	function sc(e, t, n) {
		var r = jd();
		n = {
			lane: r,
			revertLane: 0,
			gesture: null,
			action: n,
			hasEagerState: !1,
			eagerState: null,
			next: null
		}, dc(e) ? fc(t, n) : (n = Ei(e, t, n, r), n !== null && (Pd(n, e, r), pc(n, t, r)));
	}
	function cc(e, t, n) {
		lc(e, t, n, jd());
	}
	function lc(e, t, n, r) {
		var i = {
			lane: r,
			revertLane: 0,
			gesture: null,
			action: n,
			hasEagerState: !1,
			eagerState: null,
			next: null
		};
		if (dc(e)) fc(t, i);
		else {
			var a = e.alternate;
			if (e.lanes === 0 && (a === null || a.lanes === 0) && (a = t.lastRenderedReducer, a !== null)) try {
				var o = t.lastRenderedState, s = a(o, n);
				if (i.hasEagerState = !0, i.eagerState = s, Vr(s, o)) return Ti(e, t, i, 0), q === null && wi(), !1;
			} catch {}
			if (n = Ei(e, t, i, r), n !== null) return Pd(n, e, r), pc(n, t, r), !0;
		}
		return !1;
	}
	function uc(e, t, n, r) {
		if (r = {
			lane: 2,
			revertLane: Pf(),
			gesture: null,
			action: r,
			hasEagerState: !1,
			eagerState: null,
			next: null
		}, dc(e)) {
			if (t) throw Error(s(479));
		} else t = Ei(e, n, r, 2), t !== null && Pd(t, e, 2);
	}
	function dc(e) {
		var t = e.alternate;
		return e === H || t !== null && t === H;
	}
	function fc(e, t) {
		Wo = Uo = !0;
		var n = e.pending;
		n === null ? t.next = t : (t.next = n.next, n.next = t), e.pending = t;
	}
	function pc(e, t, n) {
		if (n & 4194048) {
			var r = t.lanes;
			r &= e.pendingLanes, n |= r, t.lanes = n, yt(e, n);
		}
	}
	var mc = {
		readContext: wa,
		use: ls,
		useCallback: Xo,
		useContext: Xo,
		useEffect: Xo,
		useImperativeHandle: Xo,
		useLayoutEffect: Xo,
		useInsertionEffect: Xo,
		useMemo: Xo,
		useReducer: Xo,
		useRef: Xo,
		useState: Xo,
		useDebugValue: Xo,
		useDeferredValue: Xo,
		useTransition: Xo,
		useSyncExternalStore: Xo,
		useId: Xo,
		useHostTransitionStatus: Xo,
		useFormState: Xo,
		useActionState: Xo,
		useOptimistic: Xo,
		useMemoCache: Xo,
		useCacheRefresh: Xo,
		useEffectEvent: Xo
	}, hc = {
		readContext: wa,
		use: ls,
		useCallback: function(e, t) {
			return as().memoizedState = [e, t === void 0 ? null : t], e;
		},
		useContext: wa,
		useEffect: zs,
		useImperativeHandle: function(e, t, n) {
			n = n == null ? null : n.concat([e]), Ls(4194308, 4, Gs.bind(null, t, e), n);
		},
		useLayoutEffect: function(e, t) {
			return Ls(4194308, 4, e, t);
		},
		useInsertionEffect: function(e, t) {
			Ls(4, 2, e, t);
		},
		useMemo: function(e, t) {
			var n = as();
			t = t === void 0 ? null : t;
			var r = e();
			if (Go) {
				tt(!0);
				try {
					e();
				} finally {
					tt(!1);
				}
			}
			return n.memoizedState = [r, t], r;
		},
		useReducer: function(e, t, n) {
			var r = as();
			if (n !== void 0) {
				var i = n(t);
				if (Go) {
					tt(!0);
					try {
						n(t);
					} finally {
						tt(!1);
					}
				}
			} else i = t;
			return r.memoizedState = r.baseState = i, e = {
				pending: null,
				lanes: 0,
				dispatch: null,
				lastRenderedReducer: e,
				lastRenderedState: i
			}, r.queue = e, e = e.dispatch = sc.bind(null, H, e), [r.memoizedState, e];
		},
		useRef: function(e) {
			var t = as();
			return e = { current: e }, t.memoizedState = e;
		},
		useState: function(e) {
			e = xs(e);
			var t = e.queue, n = cc.bind(null, H, t);
			return t.dispatch = n, [e.memoizedState, n];
		},
		useDebugValue: qs,
		useDeferredValue: function(e, t) {
			return Xs(as(), e, t);
		},
		useTransition: function() {
			var e = xs(!1);
			return e = Qs.bind(null, H, e.queue, !0, !1), as().memoizedState = e, [!1, e];
		},
		useSyncExternalStore: function(e, t, n) {
			var r = H, i = as();
			if (V) {
				if (n === void 0) throw Error(s(407));
				n = n();
			} else {
				if (n = t(), q === null) throw Error(s(349));
				Y & 127 || gs(r, t, n);
			}
			i.memoizedState = n;
			var a = {
				value: n,
				getSnapshot: t
			};
			return i.queue = a, zs(vs.bind(null, r, a, e), [e]), r.flags |= 2048, Fs(9, { destroy: void 0 }, _s.bind(null, r, a, n, t), null), n;
		},
		useId: function() {
			var e = as(), t = q.identifierPrefix;
			if (V) {
				var n = Zi, r = Xi;
				n = (r & ~(1 << 32 - nt(r) - 1)).toString(32) + n, t = "_" + t + "R_" + n, n = Ko++, 0 < n && (t += "H" + n.toString(32)), t += "_";
			} else n = Yo++, t = "_" + t + "r_" + n.toString(32) + "_";
			return e.memoizedState = t;
		},
		useHostTransitionStatus: rc,
		useFormState: As,
		useActionState: As,
		useOptimistic: function(e) {
			var t = as();
			t.memoizedState = t.baseState = e;
			var n = {
				pending: null,
				lanes: 0,
				dispatch: null,
				lastRenderedReducer: null,
				lastRenderedState: null
			};
			return t.queue = n, t = uc.bind(null, H, !0, n), n.dispatch = t, [e, t];
		},
		useMemoCache: us,
		useCacheRefresh: function() {
			return as().memoizedState = oc.bind(null, H);
		},
		useEffectEvent: function(e) {
			var t = as(), n = { impl: e };
			return t.memoizedState = n, function() {
				if (K & 2) throw Error(s(440));
				return n.impl.apply(void 0, arguments);
			};
		}
	}, gc = {
		readContext: wa,
		use: ls,
		useCallback: Js,
		useContext: wa,
		useEffect: Bs,
		useImperativeHandle: Ks,
		useInsertionEffect: Us,
		useLayoutEffect: Ws,
		useMemo: Ys,
		useReducer: fs,
		useRef: Is,
		useState: function() {
			return fs(ds);
		},
		useDebugValue: qs,
		useDeferredValue: function(e, t) {
			return Zs(os(), U.memoizedState, e, t);
		},
		useTransition: function() {
			var e = fs(ds)[0], t = os().memoizedState;
			return [typeof e == "boolean" ? e : cs(e), t];
		},
		useSyncExternalStore: hs,
		useId: ic,
		useHostTransitionStatus: rc,
		useFormState: js,
		useActionState: js,
		useOptimistic: function(e, t) {
			return Ss(os(), U, e, t);
		},
		useMemoCache: us,
		useCacheRefresh: ac,
		useEffectEvent: Hs
	}, _c = {
		readContext: wa,
		use: ls,
		useCallback: Js,
		useContext: wa,
		useEffect: Bs,
		useImperativeHandle: Ks,
		useInsertionEffect: Us,
		useLayoutEffect: Ws,
		useMemo: Ys,
		useReducer: ms,
		useRef: Is,
		useState: function() {
			return ms(ds);
		},
		useDebugValue: qs,
		useDeferredValue: function(e, t) {
			var n = os();
			return U === null ? Xs(n, e, t) : Zs(n, U.memoizedState, e, t);
		},
		useTransition: function() {
			var e = ms(ds)[0], t = os().memoizedState;
			return [typeof e == "boolean" ? e : cs(e), t];
		},
		useSyncExternalStore: hs,
		useId: ic,
		useHostTransitionStatus: rc,
		useFormState: Ps,
		useActionState: Ps,
		useOptimistic: function(e, t) {
			var n = os();
			return U === null ? (n.baseState = e, [e, n.queue.dispatch]) : Ss(n, U, e, t);
		},
		useMemoCache: us,
		useCacheRefresh: ac,
		useEffectEvent: Hs
	};
	function vc(e, t, n, r) {
		t = e.memoizedState, n = n(r, t), n = n == null ? t : w({}, t, n), e.memoizedState = n, e.lanes === 0 && (e.updateQueue.baseState = n);
	}
	var yc = {
		enqueueSetState: function(e, t, n) {
			e = e._reactInternals;
			var r = jd(), i = go(r);
			i.payload = t, n != null && (i.callback = n), t = _o(e, i, r), t !== null && (Pd(t, e, r), vo(t, e, r));
		},
		enqueueReplaceState: function(e, t, n) {
			e = e._reactInternals;
			var r = jd(), i = go(r);
			i.tag = 1, i.payload = t, n != null && (i.callback = n), t = _o(e, i, r), t !== null && (Pd(t, e, r), vo(t, e, r));
		},
		enqueueForceUpdate: function(e, t) {
			e = e._reactInternals;
			var n = jd(), r = go(n);
			r.tag = 2, t != null && (r.callback = t), t = _o(e, r, n), t !== null && (Pd(t, e, n), vo(t, e, n));
		}
	};
	function bc(e, t, n, r, i, a, o) {
		return e = e.stateNode, typeof e.shouldComponentUpdate == "function" ? e.shouldComponentUpdate(r, a, o) : t.prototype && t.prototype.isPureReactComponent ? !Hr(n, r) || !Hr(i, a) : !0;
	}
	function xc(e, t, n, r) {
		e = t.state, typeof t.componentWillReceiveProps == "function" && t.componentWillReceiveProps(n, r), typeof t.UNSAFE_componentWillReceiveProps == "function" && t.UNSAFE_componentWillReceiveProps(n, r), t.state !== e && yc.enqueueReplaceState(t, t.state, null);
	}
	function Sc(e, t) {
		var n = t;
		if ("ref" in t) for (var r in n = {}, t) r !== "ref" && (n[r] = t[r]);
		if (e = e.defaultProps) for (var i in n === t && (n = w({}, n)), e) n[i] === void 0 && (n[i] = e[i]);
		return n;
	}
	function Cc(e) {
		bi(e);
	}
	function wc(e) {
		console.error(e);
	}
	function Tc(e) {
		bi(e);
	}
	function Ec(e, t) {
		try {
			var n = e.onUncaughtError;
			n(t.value, { componentStack: t.stack });
		} catch (e) {
			setTimeout(function() {
				throw e;
			});
		}
	}
	function Dc(e, t, n) {
		try {
			var r = e.onCaughtError;
			r(n.value, {
				componentStack: n.stack,
				errorBoundary: t.tag === 1 ? t.stateNode : null
			});
		} catch (e) {
			setTimeout(function() {
				throw e;
			});
		}
	}
	function Oc(e, t, n) {
		return n = go(n), n.tag = 3, n.payload = { element: null }, n.callback = function() {
			Ec(e, t);
		}, n;
	}
	function kc(e) {
		return e = go(e), e.tag = 3, e;
	}
	function Ac(e, t, n, r) {
		var i = n.type.getDerivedStateFromError;
		if (typeof i == "function") {
			var a = r.value;
			e.payload = function() {
				return i(a);
			}, e.callback = function() {
				Dc(t, n, r);
			};
		}
		var o = n.stateNode;
		o !== null && typeof o.componentDidCatch == "function" && (e.callback = function() {
			Dc(t, n, r), typeof i != "function" && (vd === null ? vd = /* @__PURE__ */ new Set([this]) : vd.add(this));
			var e = r.stack;
			this.componentDidCatch(r.value, { componentStack: e === null ? "" : e });
		});
	}
	function jc(e, t, n, r, i) {
		if (n.flags |= 32768, typeof r == "object" && r && typeof r.then == "function") {
			if (t = n.alternate, t !== null && xa(t, n, i, !0), n = Ao.current, n !== null) {
				switch (n.tag) {
					case 31:
					case 13:
					case 19: return jo === null ? Kd() : n.alternate === null && ad === 0 && (ad = 3), n.flags &= -257, n.flags |= 65536, n.lanes = i, r === Za ? n.flags |= 16384 : (t = n.updateQueue, t === null ? n.updateQueue = /* @__PURE__ */ new Set([r]) : t.add(r), mf(e, r, i)), !1;
					case 22: return n.flags |= 65536, r === Za ? n.flags |= 16384 : (t = n.updateQueue, t === null ? (t = {
						transitions: null,
						markerInstances: null,
						retryQueue: /* @__PURE__ */ new Set([r])
					}, n.updateQueue = t) : (n = t.retryQueue, n === null ? t.retryQueue = /* @__PURE__ */ new Set([r]) : n.add(r)), mf(e, r, i)), !1;
				}
				throw Error(s(435, n.tag));
			}
			return mf(e, r, i), Kd(), !1;
		}
		if (V) return t = Ao.current, t === null ? (r !== oa && (t = Error(s(423), { cause: r }), pa(Hi(t, n))), e = e.current.alternate, e.flags |= 65536, i &= -i, e.lanes |= i, r = Hi(r, n), i = Oc(e.stateNode, r, i), yo(e, i), ad !== 4 && (ad = 2)) : (!(t.flags & 65536) && (t.flags |= 256), t.flags |= 65536, t.lanes = i, r !== oa && (e = Error(s(422), { cause: r }), pa(Hi(e, n)))), !1;
		var a = Error(s(520), { cause: r });
		if (a = Hi(a, n), dd === null ? dd = [a] : dd.push(a), ad !== 4 && (ad = 2), t === null) return !0;
		r = Hi(r, n), n = t;
		do {
			switch (n.tag) {
				case 3: return n.flags |= 65536, e = i & -i, n.lanes |= e, e = Oc(n.stateNode, r, e), yo(n, e), !1;
				case 1:
					if (t = n.type, a = n.stateNode, !(n.flags & 128) && (typeof t.getDerivedStateFromError == "function" || a !== null && typeof a.componentDidCatch == "function" && (vd === null || !vd.has(a)))) return n.flags |= 65536, i &= -i, n.lanes |= i, i = kc(i), Ac(i, e, n, r), yo(n, i), !1;
					break;
				case 22: if (n.memoizedState !== null) return n.flags |= 65536, !1;
			}
			n = n.return;
		} while (n !== null);
		return !1;
	}
	var Mc = Error(s(461)), Nc = !1;
	function Pc(e, t, n, r) {
		t.child = e === null ? fo(t, null, n, r) : uo(t, e.child, n, r);
	}
	function Fc(e, t, n, r, i) {
		n = n.render;
		var a = t.ref;
		if ("ref" in r) {
			var o = {};
			for (var s in r) s !== "ref" && (o[s] = r[s]);
		} else o = r;
		return Ca(t), r = Qo(e, t, n, o, a, i), s = ns(), e !== null && !Nc ? (rs(e, t, i), ll(e, t, i)) : (V && s && ea(t), t.flags |= 1, Pc(e, t, r, i), t.child);
	}
	function Ic(e, t, n, r, i) {
		if (e === null) {
			var a = n.type;
			return typeof a == "function" && !Ni(a) && a.defaultProps === void 0 && n.compare === null ? (t.tag = 15, t.type = a, Lc(e, t, a, r, i)) : (e = Ii(n.type, null, r, t, t.mode, i), e.ref = t.ref, e.return = t, t.child = e);
		}
		if (a = e.child, !ul(e, i)) {
			var o = a.memoizedProps;
			if (n = n.compare, n = n === null ? Hr : n, n(o, r) && e.ref === t.ref) return ll(e, t, i);
		}
		return t.flags |= 1, e = Pi(a, r), e.ref = t.ref, e.return = t, t.child = e;
	}
	function Lc(e, t, n, r, i) {
		if (e !== null) {
			var a = e.memoizedProps;
			if (Hr(a, r) && e.ref === t.ref) {
				if (Nc = !1, t.pendingProps = r = a, ul(e, i)) e.flags & 131072 && (Nc = !0);
				else return t.lanes = e.lanes, ll(e, t, i);
			}
		}
		return Gc(e, t, n, r, i);
	}
	function Rc(e, t, n, r) {
		var i = r.children, a = e === null ? null : e.memoizedState;
		if (e === null && t.stateNode === null && (t.stateNode = {
			_visibility: 1,
			_pendingMarkers: null,
			_retryCache: null,
			_transitions: null
		}), r.mode === "hidden") {
			if (t.flags & 128) {
				if (a = a === null ? n : a.baseLanes | n, e !== null) {
					for (r = t.child = e.child, i = 0; r !== null;) i = i | r.lanes | r.childLanes, r = r.sibling;
					r = i & ~a;
				} else r = 0, t.child = null;
				return Bc(e, t, a, n, r);
			}
			if (n & 536870912) t.memoizedState = {
				baseLanes: 0,
				cachePool: null
			}, e !== null && Ka(t, a === null ? null : a.cachePool), a === null ? Oo() : Do(t, a), Po(t);
			else return r = t.lanes = 536870912, Bc(e, t, a === null ? n : a.baseLanes | n, n, r);
		} else a === null ? (e !== null && Ka(t, null), Oo(), Fo()) : (Ka(t, a.cachePool), Do(t, a), Fo(), t.memoizedState = null);
		return Pc(e, t, i, n), t.child;
	}
	function zc(e, t) {
		return e !== null && e.tag === 22 || t.stateNode !== null || (t.stateNode = {
			_visibility: 1,
			_pendingMarkers: null,
			_retryCache: null,
			_transitions: null
		}), t.sibling;
	}
	function Bc(e, t, n, r, i) {
		var a = Ga();
		return a = a === null ? null : {
			parent: Aa._currentValue,
			pool: a
		}, t.memoizedState = {
			baseLanes: n,
			cachePool: a
		}, e !== null && Ka(t, null), Oo(), Po(t), e !== null && xa(e, t, r, !0), t.childLanes = i, null;
	}
	function Vc(e, t) {
		return t = el({
			mode: t.mode,
			children: t.children
		}, e.mode), t.ref = e.ref, e.child = t, t.return = e, t;
	}
	function Hc(e, t, n) {
		return uo(t, e.child, null, n), e = Vc(t, t.pendingProps), e.flags |= 2, Io(t), t.memoizedState = null, e;
	}
	function Uc(e, t, n) {
		var r = t.pendingProps, i = !!(t.flags & 128);
		if (t.flags &= -129, e === null) {
			if (V) {
				if (r.mode === "hidden") return e = Vc(t, r), t.lanes = 536870912, e.memoizedState = {
					baseLanes: 0,
					cachePool: null
				}, zc(null, e);
				if (No(t), (e = B) ? (e = am(e, aa), e = e !== null && e.data === "&" ? e : null, e !== null && (t.memoizedState = {
					dehydrated: e,
					treeContext: Yi === null ? null : {
						id: Xi,
						overflow: Zi
					},
					retryLane: 536870912,
					hydrationErrors: null
				}, n = zi(e), n.return = t, t.child = n, ra = t, B = null)) : e = null, e === null) throw sa(t);
				return t.lanes = 536870912, null;
			}
			return Vc(t, r);
		}
		var a = e.memoizedState;
		if (a !== null) {
			var o = a.dehydrated;
			if (No(t), i) {
				if (t.flags & 256) t.flags &= -257, t = Hc(e, t, n);
				else if (t.memoizedState !== null) t.child = e.child, t.flags |= 128, t = null;
				else throw Error(s(558));
			} else if (Nc || xa(e, t, n, !1), i = (n & e.childLanes) !== 0, Nc || i) {
				if (To.current === null) {
					if (r = q, r !== null && (o = bt(r, n), o !== 0 && o !== a.retryLane)) throw a.retryLane = o, Di(e, o), Pd(r, e, o), Mc;
					Kd();
				}
				t = Hc(e, t, n);
			} else e = a.treeContext, B = lm(o.nextSibling), ra = t, V = !0, ia = null, aa = !1, e !== null && na(t, e), t = Vc(t, r), t.flags |= 134221824;
			return t;
		}
		return e = Pi(e.child, {
			mode: r.mode,
			children: r.children
		}), e.ref = t.ref, t.child = e, e.return = t, e;
	}
	function Wc(e, t) {
		var n = t.ref;
		if (n === null) e !== null && e.ref !== null && (t.flags |= 4194816);
		else {
			if (typeof n != "function" && typeof n != "object") throw Error(s(284));
			(e === null || e.ref !== n) && (t.flags |= 4194816);
		}
	}
	function Gc(e, t, n, r, i) {
		return Ca(t), n = Qo(e, t, n, r, void 0, i), r = ns(), e !== null && !Nc ? (rs(e, t, i), ll(e, t, i)) : (V && r && ea(t), t.flags |= 1, Pc(e, t, n, i), t.child);
	}
	function Kc(e, t, n, r, i, a) {
		return Ca(t), t.updateQueue = null, n = es(t, r, n, i), $o(e), r = ns(), e !== null && !Nc ? (rs(e, t, a), ll(e, t, a)) : (V && r && ea(t), t.flags |= 1, Pc(e, t, n, a), t.child);
	}
	function qc(e, t, n, r, i) {
		if (Ca(t), t.stateNode === null) {
			var a = Ai, o = n.contextType;
			typeof o == "object" && o && (a = wa(o)), a = new n(r, a), t.memoizedState = a.state !== null && a.state !== void 0 ? a.state : null, a.updater = yc, t.stateNode = a, a._reactInternals = t, a = t.stateNode, a.props = r, a.state = t.memoizedState, a.refs = {}, mo(t), o = n.contextType, a.context = typeof o == "object" && o ? wa(o) : Ai, a.state = t.memoizedState, o = n.getDerivedStateFromProps, typeof o == "function" && (vc(t, n, o, r), a.state = t.memoizedState), typeof n.getDerivedStateFromProps == "function" || typeof a.getSnapshotBeforeUpdate == "function" || typeof a.UNSAFE_componentWillMount != "function" && typeof a.componentWillMount != "function" || (o = a.state, typeof a.componentWillMount == "function" && a.componentWillMount(), typeof a.UNSAFE_componentWillMount == "function" && a.UNSAFE_componentWillMount(), o !== a.state && yc.enqueueReplaceState(a, a.state, null), So(t, r, a, i), xo(), a.state = t.memoizedState), typeof a.componentDidMount == "function" && (t.flags |= 4194308), r = !0;
		} else if (e === null) {
			a = t.stateNode;
			var s = t.memoizedProps, c = Sc(n, s);
			a.props = c;
			var l = a.context, u = n.contextType;
			o = Ai, typeof u == "object" && u && (o = wa(u));
			var d = n.getDerivedStateFromProps;
			u = typeof d == "function" || typeof a.getSnapshotBeforeUpdate == "function", s = t.pendingProps !== s, u || typeof a.UNSAFE_componentWillReceiveProps != "function" && typeof a.componentWillReceiveProps != "function" || (s || l !== o) && xc(t, a, r, o), po = !1;
			var f = t.memoizedState;
			a.state = f, So(t, r, a, i), xo(), l = t.memoizedState, s || f !== l || po ? (typeof d == "function" && (vc(t, n, d, r), l = t.memoizedState), (c = po || bc(t, n, c, r, f, l, o)) ? (u || typeof a.UNSAFE_componentWillMount != "function" && typeof a.componentWillMount != "function" || (typeof a.componentWillMount == "function" && a.componentWillMount(), typeof a.UNSAFE_componentWillMount == "function" && a.UNSAFE_componentWillMount()), typeof a.componentDidMount == "function" && (t.flags |= 4194308)) : (typeof a.componentDidMount == "function" && (t.flags |= 4194308), t.memoizedProps = r, t.memoizedState = l), a.props = r, a.state = l, a.context = o, r = c) : (typeof a.componentDidMount == "function" && (t.flags |= 4194308), r = !1);
		} else {
			a = t.stateNode, ho(e, t), o = t.memoizedProps, u = Sc(n, o), a.props = u, d = t.pendingProps, f = a.context, l = n.contextType, c = Ai, typeof l == "object" && l && (c = wa(l)), s = n.getDerivedStateFromProps, (l = typeof s == "function" || typeof a.getSnapshotBeforeUpdate == "function") || typeof a.UNSAFE_componentWillReceiveProps != "function" && typeof a.componentWillReceiveProps != "function" || (o !== d || f !== c) && xc(t, a, r, c), po = !1, f = t.memoizedState, a.state = f, So(t, r, a, i), xo();
			var p = t.memoizedState;
			o !== d || f !== p || po || e !== null && e.dependencies !== null && Sa(e.dependencies) ? (typeof s == "function" && (vc(t, n, s, r), p = t.memoizedState), (u = po || bc(t, n, u, r, f, p, c) || e !== null && e.dependencies !== null && Sa(e.dependencies)) ? (l || typeof a.UNSAFE_componentWillUpdate != "function" && typeof a.componentWillUpdate != "function" || (typeof a.componentWillUpdate == "function" && a.componentWillUpdate(r, p, c), typeof a.UNSAFE_componentWillUpdate == "function" && a.UNSAFE_componentWillUpdate(r, p, c)), typeof a.componentDidUpdate == "function" && (t.flags |= 4), typeof a.getSnapshotBeforeUpdate == "function" && (t.flags |= 1024)) : (typeof a.componentDidUpdate != "function" || o === e.memoizedProps && f === e.memoizedState || (t.flags |= 4), typeof a.getSnapshotBeforeUpdate != "function" || o === e.memoizedProps && f === e.memoizedState || (t.flags |= 1024), t.memoizedProps = r, t.memoizedState = p), a.props = r, a.state = p, a.context = c, r = u) : (typeof a.componentDidUpdate != "function" || o === e.memoizedProps && f === e.memoizedState || (t.flags |= 4), typeof a.getSnapshotBeforeUpdate != "function" || o === e.memoizedProps && f === e.memoizedState || (t.flags |= 1024), r = !1);
		}
		return a = r, Wc(e, t), r = !!(t.flags & 128), a || r ? (a = t.stateNode, n = r && typeof n.getDerivedStateFromError != "function" ? null : a.render(), t.flags |= 1, e !== null && r ? (t.child = uo(t, e.child, null, i), t.child = uo(t, null, n, i)) : Pc(e, t, n, i), t.memoizedState = a.state, e = t.child) : e = ll(e, t, i), e;
	}
	function Jc(e, t, n, r) {
		return da(), t.flags |= 256, Pc(e, t, n, r), t.child;
	}
	var Yc = {
		dehydrated: null,
		treeContext: null,
		retryLane: 0,
		hydrationErrors: null
	};
	function Xc(e) {
		return {
			baseLanes: e,
			cachePool: qa()
		};
	}
	function Zc(e, t, n) {
		return e = e === null ? 0 : e.childLanes & ~n, t && (e |= ld), e;
	}
	function Qc(e, t, n) {
		var r = t.pendingProps, i = !1, a = !!(t.flags & 128), o;
		if ((o = a) || (o = e !== null && e.memoizedState === null ? !1 : !!(Lo.current & 2)), o && (i = !0, t.flags &= -129), o = !!(t.flags & 32), t.flags &= -33, e === null) {
			if (V) {
				if (i ? Mo(t) : Fo(), (e = B) ? (e = am(e, aa), e = e !== null && e.data !== "&" ? e : null, e !== null && (t.memoizedState = {
					dehydrated: e,
					treeContext: Yi === null ? null : {
						id: Xi,
						overflow: Zi
					},
					retryLane: 536870912,
					hydrationErrors: null
				}, n = zi(e), n.return = t, t.child = n, ra = t, B = null)) : e = null, e === null) throw sa(t);
				return t.lanes = sm(e) ? 32 : 536870912, null;
			}
			return a = r.children, r = r.fallback, i ? (Fo(), i = t.mode, a = el({
				mode: "hidden",
				children: a
			}, i), r = Li(r, i, n, null), a.return = t, r.return = t, a.sibling = r, t.child = a, r = t.child, r.memoizedState = Xc(n), r.childLanes = Zc(e, o, n), t.memoizedState = Yc, zc(null, r)) : (Mo(t), $c(t, a));
		}
		var s = e.memoizedState;
		if (s !== null) {
			var c = s.dehydrated;
			if (c !== null) return nl(e, t, a, o, r, c, s, n);
		}
		return i ? (Fo(), i = r.fallback, a = t.mode, s = e.child, c = s.sibling, r = Pi(s, {
			mode: "hidden",
			children: r.children
		}), r.subtreeFlags = s.subtreeFlags & 1206910976, c === null ? (i = Li(i, a, n, null), i.flags |= 2) : i = Pi(c, i), i.return = t, r.return = t, r.sibling = i, t.child = r, zc(null, r), r = t.child, i = e.child.memoizedState, i === null ? i = Xc(n) : (a = i.cachePool, a === null ? a = qa() : (s = Aa._currentValue, a = a.parent === s ? a : {
			parent: s,
			pool: s
		}), i = {
			baseLanes: i.baseLanes | n,
			cachePool: a
		}), r.memoizedState = i, r.childLanes = Zc(e, o, n), t.memoizedState = Yc, zc(e.child, r)) : (Mo(t), n = e.child, e = n.sibling, n = Pi(n, {
			mode: "visible",
			children: r.children
		}), n.return = t, n.sibling = null, e !== null && (o = t.deletions, o === null ? (t.deletions = [e], t.flags |= 16) : o.push(e)), t.child = n, t.memoizedState = null, n);
	}
	function $c(e, t) {
		return t = el({
			mode: "visible",
			children: t
		}, e.mode), t.return = e, e.child = t;
	}
	function el(e, t) {
		return e = Mi(22, e, null, t), e.lanes = 0, e;
	}
	function tl(e, t, n) {
		return uo(t, e.child, null, n), e = $c(t, t.pendingProps.children), e.flags |= 2, t.memoizedState = null, e;
	}
	function nl(e, t, n, r, i, a, o, c) {
		if (n) return t.flags & 256 ? (Mo(t), t.flags &= -257, tl(e, t, c)) : t.memoizedState === null ? (Fo(), a = i.fallback, o = t.mode, i = el({
			mode: "visible",
			children: i.children
		}, o), a = Li(a, o, c, null), a.flags |= 2, i.return = t, a.return = t, i.sibling = a, t.child = i, uo(t, e.child, null, c), i = t.child, i.memoizedState = Xc(c), i.childLanes = Zc(e, r, c), t.memoizedState = Yc, zc(null, i)) : (Fo(), t.child = e.child, t.flags |= 128, null);
		if (Mo(t), sm(a)) {
			if (r = a.nextSibling && a.nextSibling.dataset, r) var l = r.dgst;
			return r = l, r !== "" && (i = Error(s(419)), i.stack = "", i.digest = r, pa({
				value: i,
				source: null,
				stack: null
			})), tl(e, t, c);
		}
		if (Nc || xa(e, t, c, !1), r = (c & e.childLanes) !== 0, Nc || r) {
			if (To.current !== null) return tl(e, t, c);
			if (r = q, r !== null && (i = bt(r, c), i !== 0 && i !== o.retryLane)) throw o.retryLane = i, Di(e, i), Pd(r, e, i), Mc;
			return om(a) || Kd(), tl(e, t, c);
		}
		return om(a) ? (t.flags |= 192, t.child = e.child, null) : (e = o.treeContext, B = lm(a.nextSibling), ra = t, V = !0, ia = null, aa = !1, e !== null && na(t, e), t = $c(t, i.children), t.flags |= 134221824, t);
	}
	function rl(e, t, n) {
		e.lanes |= t;
		var r = e.alternate;
		r !== null && (r.lanes |= t), ya(e.return, t, n);
	}
	function il(e) {
		for (var t = null; e !== null;) {
			var n = e.alternate;
			n !== null && Bo(n) === null && (t = e), e = e.sibling;
		}
		return t;
	}
	function al(e, t, n, r, i, a) {
		var o = e.memoizedState;
		o === null ? e.memoizedState = {
			isBackwards: t,
			rendering: null,
			renderingStartTime: 0,
			last: r,
			tail: n,
			tailMode: i,
			treeForkCount: a
		} : (o.isBackwards = t, o.rendering = null, o.renderingStartTime = 0, o.last = r, o.tail = n, o.tailMode = i, o.treeForkCount = a);
	}
	function ol(e) {
		var t = e.child;
		for (e.child = null; t !== null;) {
			var n = t.sibling;
			t.sibling = e.child, e.child = t, t = n;
		}
	}
	function sl(e, t, n) {
		var r = t.pendingProps, i = r.revealOrder, a = r.tail;
		r = r.children;
		var o = Lo.current;
		if (t.flags & 128) return Ro(t, o), null;
		var s = !!(o & 2);
		if (s ? (o = o & 1 | 2, t.flags |= 128) : o &= 1, Ro(t, o), i === "backwards" && e !== null ? (ol(e), Pc(e, t, r, n), ol(e)) : Pc(e, t, r, n), r = V ? Ki : 0, !s && e !== null && e.flags & 128) a: for (e = t.child; e !== null;) {
			if (e.tag === 13) e.memoizedState !== null && rl(e, n, t);
			else if (e.tag === 19) rl(e, n, t);
			else if (e.child !== null) {
				e.child.return = e, e = e.child;
				continue;
			}
			if (e === t) break a;
			for (; e.sibling === null;) {
				if (e.return === null || e.return === t) break a;
				e = e.return;
			}
			e.sibling.return = e.return, e = e.sibling;
		}
		switch (i) {
			case "backwards":
				n = il(t.child), n === null ? (i = t.child, t.child = null) : (i = n.sibling, n.sibling = null, ol(t)), al(t, !0, i, null, a, r);
				break;
			case "unstable_legacy-backwards":
				for (n = null, i = t.child, t.child = null; i !== null;) {
					if (e = i.alternate, e !== null && Bo(e) === null) {
						t.child = i;
						break;
					}
					e = i.sibling, i.sibling = n, n = i, i = e;
				}
				al(t, !0, n, null, a, r);
				break;
			case "together":
				al(t, !1, null, null, void 0, r);
				break;
			case "independent":
				t.memoizedState = null;
				break;
			default: n = il(t.child), n === null ? (i = t.child, t.child = null) : (i = n.sibling, n.sibling = null), al(t, !1, i, n, a, r);
		}
		return t.child;
	}
	function cl(e, t, n) {
		var r = t.pendingProps;
		return _a(t, t.type, r.value), Pc(e, t, r.children, n), t.child;
	}
	function ll(e, t, n) {
		if (e !== null && (t.dependencies = e.dependencies), od |= t.lanes, (n & t.childLanes) === 0) {
			if (e !== null) {
				if (xa(e, t, n, !1), (n & t.childLanes) === 0) return null;
			} else return null;
		}
		if (e !== null && t.child !== e.child) throw Error(s(153));
		if (t.child !== null) {
			for (e = t.child, n = Pi(e, e.pendingProps), t.child = n, n.return = t; e.sibling !== null;) e = e.sibling, n = n.sibling = Pi(e, e.pendingProps), n.return = t;
			n.sibling = null;
		}
		return t.child;
	}
	function ul(e, t) {
		return (e.lanes & t) !== 0 || (e = e.dependencies, !!(e !== null && Sa(e)));
	}
	function dl(e, t, n) {
		switch (t.tag) {
			case 3:
				ke(t, t.stateNode.containerInfo), _a(t, Aa, e.memoizedState.cache), da();
				break;
			case 27:
			case 5:
				je(t);
				break;
			case 4:
				ke(t, t.stateNode.containerInfo);
				break;
			case 10:
				_a(t, t.type, t.memoizedProps.value);
				break;
			case 31:
				if (t.memoizedState !== null) return t.flags |= 128, No(t), null;
				break;
			case 13:
				var r = t.memoizedState;
				if (r !== null) {
					if (r.dehydrated !== null) return Mo(t), t.flags |= 128, null;
					r = xa(e, t, n, !1);
					var i = t.child.childLanes;
					return r || (n & i) !== 0 ? Qc(e, t, n) : (Mo(t), e = ll(e, t, n), e === null ? null : e.sibling);
				}
				Mo(t);
				break;
			case 19:
				if (t.flags & 128) return sl(e, t, n);
				if (i = !!(e.flags & 128), r = (n & t.childLanes) !== 0, r ||= (xa(e, t, n, !1), (n & t.childLanes) !== 0), i) {
					if (r) return sl(e, t, n);
					t.flags |= 128;
				}
				if (i = t.memoizedState, i !== null && (i.rendering = null, i.tail = null, i.lastEffect = null), Ro(t, Lo.current), r) break;
				return null;
			case 22: return t.lanes = 0, Rc(e, t, n, t.pendingProps);
			case 24: _a(t, Aa, e.memoizedState.cache);
		}
		return ll(e, t, n);
	}
	function fl(e, t, n) {
		if (e !== null) {
			if (e.memoizedProps !== t.pendingProps) Nc = !0;
			else {
				if (!ul(e, n) && !(t.flags & 128)) return Nc = !1, dl(e, t, n);
				Nc = !!(e.flags & 131072);
			}
		} else Nc = !1, V && t.flags & 1048576 && $i(t, Ki, t.index);
		switch (t.lanes = 0, t.tag) {
			case 16:
				a: {
					var r = t.pendingProps;
					if (e = eo(t.elementType), t.type = e, typeof e == "function") Ni(e) ? (r = Sc(e, r), t.tag = 1, t = qc(null, t, e, r, n)) : (t.tag = 0, t = Gc(null, t, e, r, n));
					else {
						if (e != null) {
							var i = e.$$typeof;
							if (i === ce) {
								t.tag = 11, t = Fc(null, t, e, r, n);
								break a;
							}
							if (i === ue) {
								t.tag = 14, t = Ic(null, t, e, r, n);
								break a;
							}
							if (i === se) {
								t.tag = 10, t.type = e, t = cl(null, t, n);
								break a;
							}
						}
						throw t = be(e) || e, Error(s(306, t, ""));
					}
				}
				return t;
			case 0: return Gc(e, t, t.type, t.pendingProps, n);
			case 1: return r = t.type, i = Sc(r, t.pendingProps), qc(e, t, r, i, n);
			case 3:
				a: {
					if (ke(t, t.stateNode.containerInfo), e === null) throw Error(s(387));
					r = t.pendingProps;
					var a = t.memoizedState;
					i = a.element, ho(e, t), So(t, r, null, n);
					var o = t.memoizedState;
					if (r = o.cache, _a(t, Aa, r), r !== a.cache && ba(t, [Aa], n, !0), xo(), r = o.element, a.isDehydrated) {
						if (a = {
							element: r,
							isDehydrated: !1,
							cache: o.cache
						}, t.updateQueue.baseState = a, t.memoizedState = a, t.flags & 256) {
							t = Jc(e, t, r, n);
							break a;
						}
						if (r !== i) {
							i = Hi(Error(s(424)), t), pa(i), t = Jc(e, t, r, n);
							break a;
						}
						switch (e = t.stateNode.containerInfo, e.nodeType) {
							case 9:
								e = e.body;
								break;
							default: e = e.nodeName === "HTML" ? e.ownerDocument.body : e;
						}
						for (B = lm(e.firstChild), ra = t, V = !0, ia = null, aa = !0, n = fo(t, null, r, n), t.child = n; n;) n.flags = n.flags & -3 | 134221824, n = n.sibling;
					} else {
						if (da(), r === i) {
							t = ll(e, t, n);
							break a;
						}
						Pc(e, t, r, n);
					}
					t = t.child;
				}
				return t;
			case 26: return Wc(e, t), e === null ? (n = Nm(t.type, null, t.pendingProps, null)) ? t.memoizedState = n : V || (t.stateNode = fp(t.type, t.pendingProps, De.current, t)) : t.memoizedState = Nm(t.type, e.memoizedProps, t.pendingProps, e.memoizedState), null;
			case 27: return je(t), e === null && V && (r = t.stateNode = hm(t.type, t.pendingProps, De.current), ra = t, aa = !0, i = B, Sp(t.type) ? (um = i, B = lm(r.firstChild)) : B = i), Pc(e, t, t.pendingProps.children, n), Wc(e, t), e === null && (t.flags |= 4194304), t.child;
			case 5: return e === null && V && ((i = r = B) && (r = rm(r, t.type, t.pendingProps, aa), r === null ? i = !1 : (t.stateNode = r, ra = t, B = lm(r.firstChild), aa = !1, i = !0)), i || sa(t)), je(t), i = t.type, a = t.pendingProps, o = e === null ? null : e.memoizedProps, r = a.children, pp(i, a) ? r = null : o !== null && pp(i, o) && (t.flags |= 32), t.memoizedState !== null && (i = Qo(e, t, ts, null, null, n), sh._currentValue = i), Wc(e, t), Pc(e, t, r, n), t.child;
			case 6: return e === null && V && ((e = n = B) && (n = im(n, t.pendingProps, aa), n === null ? e = !1 : (t.stateNode = n, ra = t, B = null, e = !0)), e || sa(t)), null;
			case 13: return Qc(e, t, n);
			case 4: return ke(t, t.stateNode.containerInfo), r = t.pendingProps, e === null ? t.child = uo(t, null, r, n) : Pc(e, t, r, n), t.child;
			case 11: return Fc(e, t, t.type, t.pendingProps, n);
			case 7: return r = t.pendingProps, Wc(e, t), Pc(e, t, r, n), t.child;
			case 8: return Pc(e, t, t.pendingProps.children, n), t.child;
			case 12: return Pc(e, t, t.pendingProps.children, n), t.child;
			case 10: return cl(e, t, n);
			case 9: return i = t.type._context, r = t.pendingProps.children, Ca(t), i = wa(i), r = r(i), t.flags |= 1, Pc(e, t, r, n), t.child;
			case 14: return Ic(e, t, t.type, t.pendingProps, n);
			case 15: return Lc(e, t, t.type, t.pendingProps, n);
			case 19: return sl(e, t, n);
			case 31: return Uc(e, t, n);
			case 22: return Rc(e, t, n, t.pendingProps);
			case 24: return Ca(t), r = wa(Aa), e === null ? (i = Ga(), i === null && (i = q, a = ja(), i.pooledCache = a, a.refCount++, a !== null && (i.pooledCacheLanes |= n), i = a), t.memoizedState = {
				parent: r,
				cache: i
			}, mo(t), _a(t, Aa, i)) : ((e.lanes & n) !== 0 && (ho(e, t), So(t, null, null, n), xo()), i = e.memoizedState, a = t.memoizedState, i.parent === r ? (r = a.cache, _a(t, Aa, r), r !== i.cache && ba(t, [Aa], n, !0)) : (i = {
				parent: r,
				cache: r
			}, t.memoizedState = i, t.lanes === 0 && (t.memoizedState = t.updateQueue.baseState = i), _a(t, Aa, r))), Pc(e, t, t.pendingProps.children, n), t.child;
			case 30: return t.stateNode === null && (t.stateNode = {
				autoName: null,
				paired: null,
				clones: null,
				ref: null
			}), r = t.pendingProps, r.name != null && r.name !== "auto" ? t.flags |= e === null ? 18882560 : 18874368 : V && ea(t), e !== null && e.memoizedProps.name !== r.name ? t.flags |= 4194816 : Wc(e, t), Pc(e, t, r.children, n), t.child;
			case 29: throw t.pendingProps;
		}
		throw Error(s(156, t.tag));
	}
	function pl(e) {
		e.flags |= 4;
	}
	function ml(e, t, n, r, i) {
		var a;
		if ((a = !!(e.mode & 32)) && (a = n === null ? Jm(t, r) : Jm(t, r) && (r.src !== n.src || r.srcSet !== n.srcSet)), a) {
			if (e.flags |= 16777216, (i & 335544128) === i) {
				if (e.stateNode.complete) e.flags |= 8192;
				else if (Ud()) e.flags |= 8192;
				else throw to = Za, Ya;
			}
		} else e.flags &= -16777217;
	}
	function hl(e, t) {
		if (t.type !== "stylesheet" || t.state.loading & 4) e.flags &= -16777217;
		else if (e.flags |= 16777216, !Ym(t)) {
			if (Ud()) e.flags |= 8192;
			else throw to = Za, Ya;
		}
	}
	function gl(e, t) {
		t !== null && (e.flags |= 4), e.flags & 16384 && (t = e.tag === 22 ? 536870912 : mt(), e.lanes |= t, ud |= t);
	}
	function _l(e, t) {
		if (!V) switch (e.tailMode) {
			case "visible": break;
			case "collapsed":
				for (var n = e.tail, r = null; n !== null;) n.alternate !== null && (r = n), n = n.sibling;
				r === null ? t || e.tail === null ? e.tail = null : e.tail.sibling = null : r.sibling = null;
				break;
			default:
				for (t = e.tail, n = null; t !== null;) t.alternate !== null && (n = t), t = t.sibling;
				n === null ? e.tail = null : n.sibling = null;
		}
	}
	function W(e) {
		var t = e.alternate !== null && e.alternate.child === e.child, n = 0, r = 0;
		if (t) for (var i = e.child; i !== null;) n |= i.lanes | i.childLanes, r |= i.subtreeFlags & 1206910976, r |= i.flags & 1206910976, i.return = e, i = i.sibling;
		else for (i = e.child; i !== null;) n |= i.lanes | i.childLanes, r |= i.subtreeFlags, r |= i.flags, i.return = e, i = i.sibling;
		return e.subtreeFlags |= r, e.childLanes = n, t;
	}
	function vl(e, t, n) {
		var r = t.pendingProps;
		switch (ta(t), t.tag) {
			case 16:
			case 15:
			case 0:
			case 11:
			case 7:
			case 8:
			case 12:
			case 9:
			case 14: return W(t), null;
			case 1: return W(t), null;
			case 3: return n = t.stateNode, r = null, e !== null && (r = e.memoizedState.cache), t.memoizedState.cache !== r && (t.flags |= 2048), va(Aa), Ae(), n.pendingContext && (n.context = n.pendingContext, n.pendingContext = null), (e === null || e.child === null) && (ua(t) ? pl(t) : e === null || e.memoizedState.isDehydrated && !(t.flags & 256) || (t.flags |= 1024, fa())), W(t), null;
			case 26:
				var i = t.type, a = t.memoizedState;
				return e === null ? (pl(t), a === null ? (W(t), ml(t, i, null, r, n)) : (W(t), hl(t, a))) : a ? a === e.memoizedState ? (W(t), t.flags &= -16777217) : (pl(t), W(t), hl(t, a)) : (e = e.memoizedProps, e !== r && pl(t), W(t), ml(t, i, e, r, n)), null;
			case 27:
				if (Me(t), n = De.current, i = t.type, e !== null && t.stateNode != null) e.memoizedProps !== r && pl(t);
				else {
					if (!r) {
						if (t.stateNode === null) throw Error(s(166));
						return W(t), t.subtreeFlags &= -33554433, null;
					}
					e = Te.current, ua(t) ? ca(t, e) : (e = hm(i, r, n), t.stateNode = e, pl(t));
				}
				return W(t), t.subtreeFlags &= -33554433, null;
			case 5:
				if (Me(t), i = t.type, e !== null && t.stateNode != null) e.memoizedProps !== r && pl(t);
				else {
					if (!r) {
						if (t.stateNode === null) throw Error(s(166));
						return W(t), t.subtreeFlags &= -33554433, null;
					}
					if (a = Te.current, ua(t)) ca(t, a);
					else {
						var o = lp(De.current);
						switch (a) {
							case 1:
								a = o.createElementNS("http://www.w3.org/2000/svg", i);
								break;
							case 2:
								a = o.createElementNS("http://www.w3.org/1998/Math/MathML", i);
								break;
							default: switch (i) {
								case "svg":
									a = o.createElementNS("http://www.w3.org/2000/svg", i);
									break;
								case "math":
									a = o.createElementNS("http://www.w3.org/1998/Math/MathML", i);
									break;
								case "script":
									a = o.createElement("div"), a.innerHTML = "<script><\/script>", a = a.removeChild(a.firstChild);
									break;
								case "select":
									a = typeof r.is == "string" ? o.createElement("select", { is: r.is }) : o.createElement("select"), r.multiple ? a.multiple = !0 : r.size && (a.size = r.size);
									break;
								default: a = typeof r.is == "string" ? o.createElement(i, { is: r.is }) : o.createElement(i);
							}
						}
						a[Et] = t, a[Dt] = r;
						a: for (o = t.child; o !== null;) {
							if (o.tag === 5 || o.tag === 6) a.appendChild(o.stateNode);
							else if (o.tag !== 4 && o.tag !== 27 && o.child !== null) {
								o.child.return = o, o = o.child;
								continue;
							}
							if (o === t) break a;
							for (; o.sibling === null;) {
								if (o.return === null || o.return === t) break a;
								o = o.return;
							}
							o.sibling.return = o.return, o = o.sibling;
						}
						t.stateNode = a;
						a: switch (np(a, i, r), i) {
							case "button":
							case "input":
							case "select":
							case "textarea":
								r = !!r.autoFocus;
								break a;
							case "img":
								r = !0;
								break a;
							default: r = !1;
						}
						r && pl(t);
					}
				}
				return W(t), t.subtreeFlags &= -33554433, ml(t, t.type, e === null ? null : e.memoizedProps, t.pendingProps, n), null;
			case 6:
				if (e && t.stateNode != null) e.memoizedProps !== r && pl(t);
				else {
					if (typeof r != "string" && t.stateNode === null) throw Error(s(166));
					if (e = De.current, ua(t)) {
						if (e = t.stateNode, n = t.memoizedProps, r = null, i = ra, i !== null) switch (i.tag) {
							case 27:
							case 5: r = i.memoizedProps;
						}
						e[Et] = t, e = !!(e.nodeValue === n || r !== null && !0 === r.suppressHydrationWarning || ep(e.nodeValue, n)), e || sa(t, !0);
					} else e = lp(e).createTextNode(r), e[Et] = t, t.stateNode = e;
				}
				return W(t), null;
			case 31:
				if (n = t.memoizedState, e === null || e.memoizedState !== null) {
					if (r = ua(t), n !== null) {
						if (e === null) {
							if (!r) throw Error(s(318));
							if (e = t.memoizedState, e = e === null ? null : e.dehydrated, !e) throw Error(s(557));
							e[Et] = t;
						} else da(), !(t.flags & 128) && (t.memoizedState = null), t.flags |= 4;
						W(t), e = !1;
					} else n = fa(), e !== null && e.memoizedState !== null && (e.memoizedState.hydrationErrors = n), e = !0;
					if (!e) return t.flags & 256 ? (Io(t), t) : (Io(t), null);
					if (t.flags & 128) throw Error(s(558));
				}
				return W(t), null;
			case 13:
				if (r = t.memoizedState, e === null || e.memoizedState !== null && e.memoizedState.dehydrated !== null) {
					if (i = ua(t), r !== null && r.dehydrated !== null) {
						if (e === null) {
							if (!i) throw Error(s(318));
							if (i = t.memoizedState, i = i === null ? null : i.dehydrated, !i) throw Error(s(317));
							i[Et] = t;
						} else da(), !(t.flags & 128) && (t.memoizedState = null), t.flags |= 4;
						W(t), i = !1;
					} else i = fa(), e !== null && e.memoizedState !== null && (e.memoizedState.hydrationErrors = i), i = !0;
					if (!i) return t.flags & 256 ? (Io(t), t) : (Io(t), null);
				}
				return Io(t), t.flags & 128 ? (t.lanes = n, t) : (n = r !== null, e = e !== null && e.memoizedState !== null, n && (r = t.child, i = null, r.alternate !== null && r.alternate.memoizedState !== null && r.alternate.memoizedState.cachePool !== null && (i = r.alternate.memoizedState.cachePool.pool), a = null, r.memoizedState !== null && r.memoizedState.cachePool !== null && (a = r.memoizedState.cachePool.pool), a !== i && (r.flags |= 2048)), n !== e && n && (t.child.flags |= 8192), gl(t, t.updateQueue), W(t), null);
			case 4: return Ae(), e === null && Wf(t.stateNode.containerInfo), t.flags |= 67108864, W(t), null;
			case 10: return va(t.type), W(t), null;
			case 19:
				if (zo(t), r = t.memoizedState, r === null) return W(t), null;
				if (i = !!(t.flags & 128), a = r.rendering, a === null) {
					if (i) _l(r, !1);
					else {
						if (ad !== 0 || e !== null && e.flags & 128) for (e = t.child; e !== null;) {
							if (a = Bo(e), a !== null) {
								for (t.flags |= 128, _l(r, !1), e = a.updateQueue, t.updateQueue = e, gl(t, e), t.subtreeFlags = 0, e = n, n = t.child; n !== null;) Fi(n, e), n = n.sibling;
								return Ro(t, Lo.current & 1 | 2), V && Qi(t, r.treeForkCount), t.child;
							}
							e = e.sibling;
						}
						r.tail !== null && P() > gd && (t.flags |= 128, i = !0, _l(r, !1), t.lanes = 4194304);
					}
				} else {
					if (!i) {
						if (e = Bo(a), e !== null) {
							if (t.flags |= 128, i = !0, e = e.updateQueue, t.updateQueue = e, gl(t, e), _l(r, !0), r.tail === null && r.tailMode !== "collapsed" && r.tailMode !== "visible" && !a.alternate && !V) return W(t), null;
						} else 2 * P() - r.renderingStartTime > gd && n !== 536870912 && (t.flags |= 128, i = !0, _l(r, !1), t.lanes = 4194304);
					}
					r.isBackwards ? (a.sibling = t.child, t.child = a) : (e = r.last, e === null ? t.child = a : e.sibling = a, r.last = a);
				}
				if (r.tail !== null) {
					e = r.tail;
					a: {
						for (n = e; n !== null;) {
							if (n.alternate !== null) {
								n = !1;
								break a;
							}
							n = n.sibling;
						}
						n = !0;
					}
					return r.rendering = e, r.tail = e.sibling, r.renderingStartTime = P(), e.sibling = null, a = Lo.current, a = i ? a & 1 | 2 : a & 1, r.tailMode === "visible" || r.tailMode === "collapsed" || !n || V ? Ro(t, a) : (n = a, N(Ao, t), N(Lo, n), jo === null && (jo = t)), V && Qi(t, r.treeForkCount), e;
				}
				return W(t), null;
			case 22:
			case 23: return Io(t), ko(), r = t.memoizedState !== null, e === null ? r && (t.flags |= 8192) : e.memoizedState !== null !== r && (t.flags |= 8192), r ? n & 536870912 && !(t.flags & 128) && (W(t), t.subtreeFlags & 6 && (t.flags |= 8192)) : W(t), n = t.updateQueue, n !== null && gl(t, n.retryQueue), n = null, e !== null && e.memoizedState !== null && e.memoizedState.cachePool !== null && (n = e.memoizedState.cachePool.pool), r = null, t.memoizedState !== null && t.memoizedState.cachePool !== null && (r = t.memoizedState.cachePool.pool), r !== n && (t.flags |= 2048), e !== null && M(Wa), null;
			case 24: return n = null, e !== null && (n = e.memoizedState.cache), t.memoizedState.cache !== n && (t.flags |= 2048), va(Aa), W(t), null;
			case 25: return null;
			case 30: return t.flags |= 33554432, W(t), null;
		}
		throw Error(s(156, t.tag));
	}
	function yl(e, t) {
		switch (ta(t), t.tag) {
			case 1: return e = t.flags, e & 65536 ? (t.flags = e & -65537 | 128, t) : null;
			case 3: return va(Aa), Ae(), e = t.flags, e & 65536 && !(e & 128) ? (t.flags = e & -65537 | 128, t) : null;
			case 26:
			case 27:
			case 5: return Me(t), null;
			case 31:
				if (t.memoizedState !== null) {
					if (Io(t), t.alternate === null) throw Error(s(340));
					da();
				}
				return e = t.flags, e & 65536 ? (t.flags = e & -65537 | 128, t) : null;
			case 13:
				if (Io(t), e = t.memoizedState, e !== null && e.dehydrated !== null) {
					if (t.alternate === null) throw Error(s(340));
					da();
				}
				return e = t.flags, e & 65536 ? (t.flags = e & -65537 | 128, t) : null;
			case 19: return zo(t), e = t.flags, e & 65536 ? (t.flags = e & -65537 | 128, e = t.memoizedState, e !== null && (e.rendering = null, e.tail = null), t.flags |= 4, t) : null;
			case 4: return Ae(), null;
			case 10: return va(t.type), null;
			case 22:
			case 23: return Io(t), ko(), e !== null && M(Wa), e = t.flags, e & 65536 ? (t.flags = e & -65537 | 128, t) : null;
			case 24: return va(Aa), null;
			case 25: return null;
			default: return null;
		}
	}
	function bl(e, t) {
		switch (ta(t), t.tag) {
			case 3:
				va(Aa), Ae();
				break;
			case 26:
			case 27:
			case 5:
				Me(t);
				break;
			case 4:
				Ae();
				break;
			case 31:
				t.memoizedState !== null && Io(t);
				break;
			case 13:
				Io(t);
				break;
			case 19:
				zo(t);
				break;
			case 10:
				va(t.type);
				break;
			case 22:
			case 23:
				Io(t), ko(), e !== null && M(Wa);
				break;
			case 24: va(Aa);
		}
	}
	function xl(e, t) {
		try {
			var n = t.updateQueue, r = n === null ? null : n.lastEffect;
			if (r !== null) {
				var i = r.next;
				n = i;
				do {
					if ((n.tag & e) === e) {
						r = void 0;
						var a = n.create, o = n.inst;
						r = a(), o.destroy = r;
					}
					n = n.next;
				} while (n !== i);
			}
		} catch (e) {
			Z(t, t.return, e);
		}
	}
	function Sl(e, t, n) {
		try {
			var r = t.updateQueue, i = r === null ? null : r.lastEffect;
			if (i !== null) {
				var a = i.next;
				r = a;
				do {
					if ((r.tag & e) === e) {
						var o = r.inst, s = o.destroy;
						if (s !== void 0) {
							o.destroy = void 0, i = t;
							var c = n, l = s;
							try {
								l();
							} catch (e) {
								Z(i, c, e);
							}
						}
					}
					r = r.next;
				} while (r !== a);
			}
		} catch (e) {
			Z(t, t.return, e);
		}
	}
	function Cl(e) {
		var t = e.updateQueue;
		if (t !== null) {
			var n = e.stateNode;
			try {
				wo(t, n);
			} catch (t) {
				Z(e, e.return, t);
			}
		}
	}
	function wl(e, t, n) {
		n.props = Sc(e.type, e.memoizedProps), n.state = e.memoizedState;
		try {
			n.componentWillUnmount();
		} catch (n) {
			Z(e, t, n);
		}
	}
	function Tl(e, t) {
		try {
			var n = e.ref;
			if (n !== null) {
				switch (e.tag) {
					case 26:
					case 27:
					case 5:
						var r = e.stateNode;
						break;
					case 30:
						var i = e.stateNode, a = _i(e.memoizedProps, i);
						(i.ref === null || i.ref.name !== a) && (i.ref = Pp(a)), r = i.ref;
						break;
					case 7:
						if (e.stateNode === null) {
							var o = new Fp(e);
							h(e.child, !1, Qp, o, void 0, void 0), e.stateNode = o;
						}
						r = e.stateNode;
						break;
					default: r = e.stateNode;
				}
				typeof n == "function" ? e.refCleanup = n(r) : n.current = r;
			}
		} catch (n) {
			Z(e, t, n);
		}
	}
	function El(e, t) {
		var n = e.ref, r = e.refCleanup;
		if (n !== null) {
			if (typeof r == "function") try {
				r();
			} catch (n) {
				Z(e, t, n);
			} finally {
				e.refCleanup = null, e = e.alternate, e != null && (e.refCleanup = null);
			}
			else if (typeof n == "function") try {
				n(null);
			} catch (n) {
				Z(e, t, n);
			}
			else n.current = null;
		}
	}
	function Dl(e, t) {
		if ((e.tag === 5 || e.tag === 27 || e.tag === 6) && e.alternate === null && t !== null) for (var n = 0; n < t.length; n++) em(e.stateNode, t[n]);
	}
	function Ol(e) {
		for (var t = e.return; t !== null && (jl(t) && em(e.stateNode, t.stateNode), !Al(t));) t = t.return;
	}
	function kl(e) {
		for (var t = e.return; t !== null && (jl(t) && tm(e.stateNode, t.stateNode), !Al(t));) t = t.return;
	}
	function Al(e) {
		return e.tag === 5 || e.tag === 3 || e.tag === 27;
	}
	function jl(e) {
		return e && e.tag === 7 && e.stateNode !== null;
	}
	function Ml(e) {
		var t = e.type, n = e.memoizedProps, r = e.stateNode;
		try {
			a: switch (t) {
				case "button":
				case "input":
				case "select":
				case "textarea":
					n.autoFocus && r.focus();
					break a;
				case "img": n.src ? r.src = n.src : n.srcSet && (r.srcset = n.srcSet);
			}
		} catch (t) {
			Z(e, e.return, t);
		}
	}
	function Nl(e, t, n) {
		try {
			var r = e.stateNode;
			ip(r, e.type, n, t), r[Dt] = t;
		} catch (t) {
			Z(e, e.return, t);
		}
	}
	function Pl(e) {
		return e.tag === 5 || e.tag === 3 || e.tag === 26 || e.tag === 27 && Sp(e.type) || e.tag === 4;
	}
	function Fl(e) {
		a: for (;;) {
			for (; e.sibling === null;) {
				if (e.return === null || Pl(e.return)) return null;
				e = e.return;
			}
			for (e.sibling.return = e.return, e = e.sibling; e.tag !== 5 && e.tag !== 6 && e.tag !== 18;) {
				if (e.tag === 27 && Sp(e.type) || e.flags & 2 || e.child === null || e.tag === 4) continue a;
				e.child.return = e, e = e.child;
			}
			if (!(e.flags & 2)) return e.stateNode;
		}
	}
	function Il(e, t, n, r) {
		var i = e.tag;
		if (i === 5 || i === 6) i = e.stateNode, t ? (n.nodeType === 9 ? n.body : n.nodeName === "HTML" ? n.ownerDocument.body : n).insertBefore(i, t) : (t = n.nodeType === 9 ? n.body : n.nodeName === "HTML" ? n.ownerDocument.body : n, t.appendChild(i), n = n._reactRootContainer, n != null || t.onclick !== null || (t.onclick = vn)), Dl(e, r), z = !0;
		else if (i !== 4 && (i === 27 && (Dl(e, r), r = null, Sp(e.type) && (n = e.stateNode, t = null)), e = e.child, e !== null)) for (Il(e, t, n, r), e = e.sibling; e !== null;) Il(e, t, n, r), e = e.sibling;
	}
	function Ll(e, t, n, r) {
		var i = e.tag;
		if (i === 5 || i === 6) i = e.stateNode, t ? n.insertBefore(i, t) : n.appendChild(i), Dl(e, r), z = !0;
		else if (i !== 4 && (i === 27 && (Dl(e, r), r = null, Sp(e.type) && (n = e.stateNode)), e = e.child, e !== null)) for (Ll(e, t, n, r), e = e.sibling; e !== null;) Ll(e, t, n, r), e = e.sibling;
	}
	function Rl(e) {
		var t = e.stateNode, n = e.memoizedProps;
		try {
			for (var r = e.type, i = t.attributes; i.length;) t.removeAttributeNode(i[0]);
			np(t, r, n), t[Et] = e, t[Dt] = n;
		} catch (t) {
			Z(e, e.return, t);
		}
	}
	var zl = !1, Bl = null;
	function Vl(e) {
		(e.tag === 30 || e.subtreeFlags & 33554432) && (zl = !0);
	}
	var Hl = null;
	function Ul() {
		var e = Hl;
		return Hl = null, e;
	}
	var Wl = 0;
	function Gl(e, t, n, r, i) {
		return Wl = 0, Kl(e.child, t, n, r, i);
	}
	function Kl(e, t, n, r, i) {
		for (var a = !1; e !== null;) {
			if (e.tag === 5) {
				var o = e.stateNode;
				if (r !== null) {
					var s = Op(o);
					r.push(s), s.view && (a = !0);
				} else a || Op(o).view && (a = !0);
				zl = !0, Tp(o, Wl === 0 ? t : t + "_" + Wl, n), Wl++;
			} else e.tag === 22 && e.memoizedState !== null || e.tag === 30 && i || Kl(e.child, t, n, r, i) && (a = !0);
			e = e.sibling;
		}
		return a;
	}
	function ql(e, t) {
		for (; e !== null;) e.tag === 5 ? Ep(e.stateNode, e.memoizedProps) : e.tag === 22 && e.memoizedState !== null || e.tag === 30 && t || ql(e.child, t), e = e.sibling;
	}
	function Jl(e) {
		if (e.subtreeFlags & 18874368) for (e = e.child; e !== null;) {
			if ((e.tag !== 22 || e.memoizedState === null) && (Jl(e), e.tag === 30 && e.flags & 18874368 && e.stateNode.paired)) {
				var t = e.memoizedProps;
				if (t.name == null || t.name === "auto") throw Error(s(544));
				var n = t.name;
				t = yi(t.default, t.share), t !== "none" && (Gl(e, n, t, null, !1) || ql(e.child, !1));
			}
			e = e.sibling;
		}
	}
	function Yl(e, t) {
		if (e.tag === 30) {
			var n = e.stateNode, r = e.memoizedProps, i = _i(r, n), a = yi(r.default, n.paired ? r.share : r.enter);
			a === "none" ? Jl(e) : Gl(e, i, a, null, !1) ? (Jl(e), n.paired || t || Nd(e, r.onEnter)) : ql(e.child, !1);
		} else if (e.subtreeFlags & 33554432) for (e = e.child; e !== null;) Yl(e, t), e = e.sibling;
		else Jl(e);
	}
	function Xl(e) {
		if (Bl !== null && Bl.size !== 0) {
			var t = Bl;
			if (e.subtreeFlags & 18874368) for (e = e.child; e !== null;) {
				if (e.tag !== 22 || e.memoizedState === null) {
					if (e.tag === 30 && e.flags & 18874368) {
						var n = e.memoizedProps, r = n.name;
						if (r != null && r !== "auto") {
							var i = t.get(r);
							if (i !== void 0) {
								var a = yi(n.default, n.share);
								if (a !== "none" && (Gl(e, r, a, null, !1) ? (a = e.stateNode, i.paired = a, a.paired = i, Nd(e, n.onShare)) : ql(e.child, !1)), t.delete(r), t.size === 0) break;
							}
						}
					}
					Xl(e);
				}
				e = e.sibling;
			}
		}
	}
	function Zl(e) {
		if (e.tag === 30) {
			var t = e.memoizedProps, n = _i(t, e.stateNode), r = Bl === null ? void 0 : Bl.get(n), i = yi(t.default, r === void 0 ? t.exit : t.share);
			i !== "none" && (Gl(e, n, i, null, !1) ? r === void 0 ? Nd(e, t.onExit) : (i = e.stateNode, r.paired = i, i.paired = r, Bl.delete(n), Nd(e, t.onShare)) : ql(e.child, !1)), Bl !== null && Xl(e);
		} else if (e.subtreeFlags & 33554432) for (e = e.child; e !== null;) Zl(e), e = e.sibling;
		else Bl !== null && Xl(e);
	}
	function Ql(e) {
		for (e = e.child; e !== null;) {
			if (e.tag === 30) {
				var t = e.memoizedProps, n = _i(t, e.stateNode);
				t = yi(t.default, t.update), e.flags &= -5, t !== "none" && Gl(e, n, t, e.memoizedState = [], !1);
			} else e.subtreeFlags & 33554432 && Ql(e);
			e = e.sibling;
		}
	}
	function $l(e) {
		if (e.subtreeFlags & 18874368) for (e = e.child; e !== null;) {
			if (e.tag !== 22 || e.memoizedState === null) {
				if (e.tag === 30 && e.flags & 18874368) {
					var t = e.stateNode;
					t.paired !== null && (t.paired = null, ql(e.child, !1));
				}
				$l(e);
			}
			e = e.sibling;
		}
	}
	function eu(e) {
		if (e.tag === 30) e.stateNode.paired = null, ql(e.child, !1), $l(e);
		else if (e.subtreeFlags & 33554432) for (e = e.child; e !== null;) eu(e), e = e.sibling;
		else $l(e);
	}
	function tu(e) {
		for (e = e.child; e !== null;) e.tag === 30 ? ql(e.child, !1) : e.subtreeFlags & 33554432 && tu(e), e = e.sibling;
	}
	function nu(e, t, n, r, i, a, o) {
		for (var s = !1; t !== null;) {
			if (t.tag === 5) {
				var c = t.stateNode;
				if (a !== null && Wl < a.length) {
					var l = a[Wl], u = Op(c);
					(l.view || u.view) && (s = !0);
					var d;
					if (d = !(e.flags & 4)) {
						if (u.clip) d = !0;
						else {
							d = l.rect;
							var f = u.rect;
							d = d.y !== f.y || d.x !== f.x || d.height !== f.height || d.width !== f.width;
						}
					}
					d && (e.flags |= 4), u.abs ? u = !l.abs : (l = l.rect, u = u.rect, u = l.height !== u.height || l.width !== u.width), u && (e.flags |= 32);
				} else e.flags |= 32;
				e.flags & 4 && Tp(c, Wl === 0 ? n : n + "_" + Wl, i), s && e.flags & 4 || (Hl === null && (Hl = []), Hl.push(c, Wl === 0 ? r : r + "_" + Wl, t.memoizedProps)), Wl++;
			} else (t.tag !== 22 || t.memoizedState === null) && (t.tag === 30 && o ? e.flags |= t.flags & 32 : nu(e, t.child, n, r, i, a, o) && (s = !0));
			t = t.sibling;
		}
		return s;
	}
	function ru(e, t) {
		for (e = e.child; e !== null;) {
			if (e.tag === 30) {
				var n = e.memoizedProps, r = e.stateNode, i = _i(n, r), a = yi(n.default, n.update);
				if (t) {
					r = r.clones;
					var o = r === null ? null : r.map(kp);
				} else o = e.memoizedState, e.memoizedState = null;
				r = e;
				var s = e.child;
				Wl = 0, i = nu(r, s, i, i, a, o, !1), e.flags & 4 && i && (t || Nd(e, n.onUpdate));
			} else e.subtreeFlags & 33554432 && ru(e, t);
			e = e.sibling;
		}
	}
	var iu = !1, G = !1, au = !1, ou = !1, su = typeof WeakSet == "function" ? WeakSet : Set, cu = null, lu = !1, uu = !1, du = !1, fu = !1;
	function pu(e, t, n) {
		if (e = e.containerInfo, sp = gh, e = qr(e), Jr(e)) {
			if ("selectionStart" in e) var r = {
				start: e.selectionStart,
				end: e.selectionEnd
			};
			else a: {
				r = (r = e.ownerDocument) && r.defaultView || window;
				var i = r.getSelection && r.getSelection();
				if (i && i.rangeCount !== 0) {
					r = i.anchorNode;
					var a = i.anchorOffset, o = i.focusNode;
					i = i.focusOffset;
					try {
						r.nodeType, o.nodeType;
					} catch {
						r = null;
						break a;
					}
					var s = 0, c = -1, l = -1, u = 0, d = 0, f = e, p = null;
					b: for (;;) {
						for (var m; f !== r || a !== 0 && f.nodeType !== 3 || (c = s + a), f !== o || i !== 0 && f.nodeType !== 3 || (l = s + i), f.nodeType === 3 && (s += f.nodeValue.length), (m = f.firstChild) !== null;) p = f, f = m;
						for (;;) {
							if (f === e) break b;
							if (p === r && ++u === a && (c = s), p === o && ++d === i && (l = s), (m = f.nextSibling) !== null) break;
							f = p, p = f.parentNode;
						}
						f = m;
					}
					r = c === -1 || l === -1 ? null : {
						start: c,
						end: l
					};
				} else r = null;
			}
			r ||= {
				start: 0,
				end: 0
			};
		} else r = null;
		for (cp = {
			focusedElem: e,
			selectionRange: r
		}, gh = !1, n = (n & 335544064) === n, cu = t, t = n ? 9270 : 1024; cu !== null;) {
			if (e = cu, n && (r = e.deletions, r !== null)) for (a = 0; a < r.length; a++) n && Zl(r[a]);
			if (e.alternate === null && e.flags & 2) n && Vl(e), mu(n);
			else {
				if (e.tag === 22) {
					if (r = e.alternate, e.memoizedState !== null) {
						r !== null && r.memoizedState === null && n && Zl(r), mu(n);
						continue;
					}
					if (r !== null && r.memoizedState !== null) {
						n && Vl(e), mu(n);
						continue;
					}
				}
				r = e.child, (e.subtreeFlags & t) !== 0 && r !== null ? (r.return = e, cu = r) : (n && Ql(e), mu(n));
			}
		}
		Bl = null;
	}
	function mu(e) {
		for (; cu !== null;) {
			var t = cu, n = e, r = t.alternate, i = t.flags;
			switch (t.tag) {
				case 0:
				case 11:
				case 15: break;
				case 1:
					if (i & 1024 && r !== null) {
						n = void 0, i = r.memoizedProps, r = r.memoizedState;
						var a = t.stateNode;
						try {
							var o = Sc(t.type, i);
							n = a.getSnapshotBeforeUpdate(o, r), a.__reactInternalSnapshotBeforeUpdate = n;
						} catch (e) {
							Z(t, t.return, e);
						}
					}
					break;
				case 3:
					if (i & 1024) {
						if (r = t.stateNode.containerInfo, n = r.nodeType, n === 9) nm(r);
						else if (n === 1) switch (r.nodeName) {
							case "HEAD":
							case "HTML":
							case "BODY":
								nm(r);
								break;
							default: r.textContent = "";
						}
					}
					break;
				case 5:
				case 26:
				case 27:
				case 6:
				case 4:
				case 17: break;
				case 30:
					n && r !== null && (n = _i(r.memoizedProps, r.stateNode), i = t.memoizedProps, i = yi(i.default, i.update), i !== "none" && Gl(r, n, i, r.memoizedState = [], !0));
					break;
				default: if (i & 1024) throw Error(s(163));
			}
			if (r = t.sibling, r !== null) {
				r.return = t.return, cu = r;
				break;
			}
			cu = t.return;
		}
	}
	function hu(e, t, n) {
		var r = n.flags;
		switch (n.tag) {
			case 0:
			case 11:
			case 15:
				Fu(e, n), r & 4 && xl(5, n);
				break;
			case 1:
				if (Fu(e, n), r & 4) {
					if (e = n.stateNode, t === null) try {
						e.componentDidMount();
					} catch (e) {
						Z(n, n.return, e);
					}
					else {
						var i = Sc(n.type, t.memoizedProps);
						t = t.memoizedState;
						try {
							e.componentDidUpdate(i, t, e.__reactInternalSnapshotBeforeUpdate);
						} catch (e) {
							Z(n, n.return, e);
						}
					}
				}
				r & 64 && Cl(n), r & 512 && Tl(n, n.return);
				break;
			case 3:
				if (Fu(e, n), r & 64 && (e = n.updateQueue, e !== null)) {
					if (t = null, n.child !== null) switch (n.child.tag) {
						case 27:
						case 5:
							t = n.child.stateNode;
							break;
						case 1: t = n.child.stateNode;
					}
					try {
						wo(e, t);
					} catch (e) {
						Z(n, n.return, e);
					}
				}
				break;
			case 27: t === null && r & 4 && Rl(n);
			case 26:
			case 5:
				Fu(e, n), t === null && r & 4 && Ml(n), r & 512 && Tl(n, n.return);
				break;
			case 12:
				Fu(e, n);
				break;
			case 31:
				Fu(e, n), r & 4 && wu(e, n);
				break;
			case 13:
				Fu(e, n), r & 4 && Tu(e, n), r & 64 && (e = n.memoizedState, e !== null && (e = e.dehydrated, e !== null && (n = _f.bind(null, n), cm(e, n))));
				break;
			case 22:
				if (r = n.memoizedState !== null || iu, !r) {
					var a = t !== null && t.memoizedState !== null || G;
					t = iu, i = G, iu = r, (G = a) && !i ? (r = 2, n.subtreeFlags & 8772 && (r |= 1), Lu(e, n, r)) : Fu(e, n), iu = t, G = i;
				}
				break;
			case 30:
				Fu(e, n), r & 512 && Tl(n, n.return);
				break;
			case 7: r & 512 && Tl(n, n.return);
			default: Fu(e, n);
		}
	}
	function gu(e, t) {
		for (e = e.child; e !== null;) _u(e, t), e = e.sibling;
	}
	function _u(e, t) {
		switch (e.tag) {
			case 5:
			case 26:
				try {
					var n = e.stateNode;
					if (t) {
						var r = n.style;
						typeof r.setProperty == "function" ? r.setProperty("display", "none", "important") : r.display = "none";
					} else {
						var i = e.stateNode, a = e.memoizedProps.style, o = a != null && a.hasOwnProperty("display") ? a.display : null;
						i.style.display = o == null || typeof o == "boolean" ? "" : ("" + o).trim();
					}
				} catch (t) {
					Z(e, e.return, t);
				}
				vu(e, t);
				break;
			case 6:
				try {
					e.stateNode.nodeValue = t ? "" : e.memoizedProps, z = !0;
				} catch (t) {
					Z(e, e.return, t);
				}
				break;
			case 18:
				try {
					var s = e.stateNode;
					t ? wp(s, !0) : wp(e.stateNode, !1);
				} catch (t) {
					Z(e, e.return, t);
				}
				break;
			case 22:
			case 23:
				e.memoizedState === null && gu(e, t);
				break;
			default: gu(e, t);
		}
	}
	function vu(e, t) {
		if (e.subtreeFlags & 67108864) for (e = e.child; e !== null;) {
			a: {
				var n = e, r = t;
				switch (n.tag) {
					case 4:
						_u(n, r);
						break a;
					case 22:
						n.memoizedState === null && vu(n, r);
						break a;
					default: vu(n, r);
				}
			}
			e = e.sibling;
		}
	}
	function yu(e) {
		var t = e.alternate;
		t !== null && (e.alternate = null, yu(t)), e.child = null, e.deletions = null, e.sibling = null, e.tag === 5 && (t = e.stateNode, t !== null && Ft(t)), e.stateNode = null, e.return = null, e.dependencies = null, e.memoizedProps = null, e.memoizedState = null, e.pendingProps = null, e.stateNode = null, e.updateQueue = null;
	}
	var bu = null, xu = !1;
	function Su(e, t, n) {
		for (n = n.child; n !== null;) Cu(e, t, n), n = n.sibling;
	}
	function Cu(e, t, n) {
		if (et && typeof et.onCommitFiberUnmount == "function") try {
			et.onCommitFiberUnmount($e, n);
		} catch {}
		switch (n.tag) {
			case 26:
				G || El(n, t), Su(e, t, n), n.memoizedState ? n.memoizedState.count-- : n.stateNode && !G && (n = n.stateNode, n.parentNode.removeChild(n));
				break;
			case 27:
				G || El(n, t), kl(n);
				var r = bu, i = xu;
				Sp(n.type) && (bu = n.stateNode, xu = !1), Su(e, t, n), gm(n.stateNode, n.type, n.memoizedProps), bu = r, xu = i;
				break;
			case 5: G || El(n, t), kl(n);
			case 6:
				if (n.tag === 6 && kl(n), r = bu, i = xu, bu = null, Su(e, t, n), bu = r, xu = i, bu !== null) {
					if (xu) try {
						(bu.nodeType === 9 ? bu.body : bu.nodeName === "HTML" ? bu.ownerDocument.body : bu).removeChild(n.stateNode), z = !0;
					} catch (e) {
						Z(n, t, e);
					}
					else try {
						bu.removeChild(n.stateNode), z = !0;
					} catch (e) {
						Z(n, t, e);
					}
				}
				break;
			case 18:
				bu !== null && (xu ? (e = bu, Cp(e.nodeType === 9 ? e.body : e.nodeName === "HTML" ? e.ownerDocument.body : e, n.stateNode), Hh(e)) : Cp(bu, n.stateNode));
				break;
			case 4:
				r = bu, i = xu, bu = n.stateNode.containerInfo, xu = !0, Su(e, t, n), bu = r, xu = i;
				break;
			case 0:
			case 11:
			case 14:
			case 15:
				Sl(2, n, t), G || Sl(4, n, t), Su(e, t, n);
				break;
			case 1:
				G || (El(n, t), r = n.stateNode, typeof r.componentWillUnmount == "function" && wl(n, t, r)), Su(e, t, n);
				break;
			case 21:
				Su(e, t, n);
				break;
			case 22:
				G = (r = G) || n.memoizedState !== null, Su(e, t, n), G = r;
				break;
			case 30:
				El(n, t), Su(e, t, n);
				break;
			case 7:
				G || El(n, t), Su(e, t, n);
				break;
			default: Su(e, t, n);
		}
	}
	function wu(e, t) {
		if (t.memoizedState === null && (e = t.alternate, e !== null && (e = e.memoizedState, e !== null))) {
			e = e.dehydrated;
			try {
				Hh(e);
			} catch (e) {
				Z(t, t.return, e);
			}
		}
	}
	function Tu(e, t) {
		if (t.memoizedState === null && (e = t.alternate, e !== null && (e = e.memoizedState, e !== null && (e = e.dehydrated, e !== null)))) try {
			Hh(e);
		} catch (e) {
			Z(t, t.return, e);
		}
	}
	function Eu(e) {
		switch (e.tag) {
			case 31:
			case 13:
			case 19:
				var t = e.stateNode;
				return t === null && (t = e.stateNode = new su()), t;
			case 22: return e = e.stateNode, t = e._retryCache, t === null && (t = e._retryCache = new su()), t;
			default: throw Error(s(435, e.tag));
		}
	}
	function Du(e, t) {
		var n = Eu(e);
		t.forEach(function(t) {
			if (!n.has(t)) {
				n.add(t);
				var r = vf.bind(null, e, t);
				t.then(r, r);
			}
		});
	}
	function Ou(e, t, n) {
		var r = t.deletions;
		if (r !== null) for (var i = 0; i < r.length; i++) {
			var a = r[i], o = e, c = t, l = c;
			a: for (; l !== null;) {
				switch (l.tag) {
					case 27:
						if (Sp(l.type)) {
							bu = l.stateNode, xu = !1;
							break a;
						}
						break;
					case 5:
						bu = l.stateNode, xu = !1;
						break a;
					case 3:
					case 4:
						bu = l.stateNode.containerInfo, xu = !0;
						break a;
				}
				l = l.return;
			}
			if (bu === null) throw Error(s(160));
			Cu(o, c, a), bu = null, xu = !1, o = a.alternate, o !== null && (o.return = null), a.return = null;
		}
		if (t.subtreeFlags & 13886) for (t = t.child; t !== null;) Au(t, e, n), t = t.sibling;
	}
	var ku = null;
	function Au(e, t, n) {
		var r = e.alternate, i = e.flags;
		switch (e.tag) {
			case 0:
			case 11:
			case 14:
			case 15:
				if (i & 4 && (r = e.updateQueue, r = r === null ? null : r.events, r !== null)) for (var a = 0; a < r.length; a++) {
					var o = r[a];
					o.ref.impl = o.nextImpl;
				}
				Ou(t, e, n), ju(e), i & 4 && (Sl(3, e, e.return), xl(3, e), Sl(5, e, e.return));
				break;
			case 1:
				Ou(t, e, n), ju(e), i & 512 && (G || r === null || El(r, r.return)), i & 64 && iu && (e = e.updateQueue, e !== null && (t = e.callbacks, t !== null && (n = e.shared.hiddenCallbacks, e.shared.hiddenCallbacks = n === null ? t : n.concat(t))));
				break;
			case 26:
				if (a = ku, Ou(t, e, n), ju(e), i & 512 && (G || r === null || El(r, r.return)), i & 4) {
					if (i = r === null ? null : r.memoizedState, n = e.memoizedState, r === null) {
						if (n === null) {
							if (e.stateNode === null) {
								if (iu) e.stateNode = fp(e.type, e.memoizedProps, t.containerInfo, e);
								else {
									a: {
										t = e.type, n = e.memoizedProps, i = a.ownerDocument || a;
										b: switch (t) {
											case "title":
												r = i.getElementsByTagName("title")[0], (!r || r[Nt] || r[Et] || r.namespaceURI === "http://www.w3.org/2000/svg" || r.hasAttribute("itemprop")) && (r = i.createElement(t), i.head.insertBefore(r, i.querySelector("head > title"))), np(r, t, n), r[Et] = e, L(r), t = r;
												break a;
											case "link":
												if (a = Gm("link", "href", i).get(t + (n.href || ""))) {
													for (o = 0; o < a.length; o++) if (r = a[o], r.getAttribute("href") === (n.href == null || n.href === "" ? null : n.href) && r.getAttribute("rel") === (n.rel == null ? null : n.rel) && r.getAttribute("title") === (n.title == null ? null : n.title) && r.getAttribute("crossorigin") === (n.crossOrigin == null ? null : n.crossOrigin)) {
														a.splice(o, 1);
														break b;
													}
												}
												r = i.createElement(t), np(r, t, n), i.head.appendChild(r);
												break;
											case "meta":
												if (a = Gm("meta", "content", i).get(t + (n.content || ""))) {
													for (o = 0; o < a.length; o++) if (r = a[o], r.getAttribute("content") === (n.content == null ? null : "" + n.content) && r.getAttribute("name") === (n.name == null ? null : n.name) && r.getAttribute("property") === (n.property == null ? null : n.property) && r.getAttribute("http-equiv") === (n.httpEquiv == null ? null : n.httpEquiv) && r.getAttribute("charset") === (n.charSet == null ? null : n.charSet)) {
														a.splice(o, 1);
														break b;
													}
												}
												r = i.createElement(t), np(r, t, n), i.head.appendChild(r);
												break;
											default: throw Error(s(468, t));
										}
										r[Et] = e, L(r), t = r;
									}
									e.stateNode = t;
								}
							} else iu || Km(a, e.type, e.stateNode);
						} else e.stateNode = Bm(a, n, e.memoizedProps);
					} else i === n ? n === null && e.stateNode !== null && Nl(e, e.memoizedProps, r.memoizedProps) : (i === null ? (t = r.stateNode, t === null || G || t.parentNode.removeChild(t)) : i.count--, n === null ? iu || Km(a, e.type, e.stateNode) : Bm(a, n, e.memoizedProps));
				}
				break;
			case 27:
				Ou(t, e, n), ju(e), i & 512 && (G || r === null || El(r, r.return)), r !== null && i & 4 && Nl(e, e.memoizedProps, r.memoizedProps);
				break;
			case 5:
				if (a = au, au = !1, Ou(t, e, n), au = a, ju(e), i & 512 && (G || r === null || El(r, r.return)), e.flags & 32) {
					t = e.stateNode;
					try {
						un(t, ""), z = !0;
					} catch (t) {
						Z(e, e.return, t);
					}
				}
				i & 4 && e.stateNode != null && (t = e.memoizedProps, Nl(e, t, r === null ? t : r.memoizedProps)), i & 1024 && (ou = !0);
				break;
			case 6:
				if (Ou(t, e, n), ju(e), i & 4) {
					if (e.stateNode === null) throw Error(s(162));
					t = e.memoizedProps, n = e.stateNode;
					try {
						n.nodeValue = t, z = !0;
					} catch (t) {
						Z(e, e.return, t);
					}
				}
				break;
			case 3:
				if (z = !1, Wm = null, a = ku, ku = bm(t.containerInfo), Ou(t, e, n), ku = a, ju(e), i & 4 && r !== null && r.memoizedState.isDehydrated) try {
					Hh(t.containerInfo);
				} catch (t) {
					Z(e, e.return, t);
				}
				ou && (ou = !1, Mu(e)), z = !1;
				break;
			case 4:
				i = au, au = iu, r = Kt(), a = ku, ku = bm(e.stateNode.containerInfo), Ou(t, e, n), ju(e), ku = a, z && uu && (du = !0), z = r, au = i;
				break;
			case 12:
				Ou(t, e, n), ju(e);
				break;
			case 31:
				Ou(t, e, n), ju(e), i & 4 && (t = e.updateQueue, t !== null && (e.updateQueue = null, Du(e, t)));
				break;
			case 13:
				Ou(t, e, n), ju(e), e.child.flags & 8192 && e.memoizedState !== null != (r !== null && r.memoizedState !== null) && (md = P()), i & 4 && (t = e.updateQueue, t !== null && (e.updateQueue = null, Du(e, t)));
				break;
			case 22:
				a = e.memoizedState !== null, o = r !== null && r.memoizedState !== null;
				var c = iu, l = G, u = au;
				iu = c || a, au = u || a, G = l || o, Ou(t, e, n), G = l, au = u, iu = c, ju(e), i & 8192 && (t = e.stateNode, t._visibility = a ? t._visibility & -2 : t._visibility | 1, !a || r === null || o || iu || G || (t = o || G, n = iu, r = G, iu = a || iu, G = t, Iu(e, 2), iu = n, G = r), !a && au || gu(e, a)), i & 4 && (t = e.updateQueue, t !== null && (n = t.retryQueue, n !== null && (t.retryQueue = null, Du(e, n))));
				break;
			case 19:
				Ou(t, e, n), ju(e), i & 4 && (t = e.updateQueue, t !== null && (e.updateQueue = null, Du(e, t)));
				break;
			case 30:
				i & 512 && (G || r === null || El(r, r.return)), i = Kt(), a = uu, o = (n & 335544064) === n, c = e.memoizedProps, uu = o && yi(c.default, c.update) !== "none", Ou(t, e, n), ju(e), o && r !== null && z && (e.flags |= 4), uu = a, z = i;
				break;
			case 21: break;
			case 7: i & 512 && (G || r === null || El(r, r.return)), r && r.stateNode !== null && (r.stateNode._fragmentFiber = e);
			default: Ou(t, e, n), ju(e);
		}
	}
	function ju(e) {
		var t = e.flags;
		if (t & 2) {
			try {
				for (var n, r = e.return; r !== null;) {
					if (Pl(r)) {
						n = r;
						break;
					}
					r = r.return;
				}
				r = null;
				for (var i = e.return; i !== null;) {
					if (jl(i)) {
						var a = i.stateNode;
						r === null ? r = [a] : r.push(a);
					}
					if (Al(i)) break;
					i = i.return;
				}
				var o = r;
				if (n == null) throw Error(s(160));
				switch (n.tag) {
					case 27:
						var c = n.stateNode;
						Ll(e, Fl(e), c, o);
						break;
					case 5:
						var l = n.stateNode;
						n.flags & 32 && (un(l, ""), n.flags &= -33), Ll(e, Fl(e), l, o);
						break;
					case 3:
					case 4:
						var u = n.stateNode.containerInfo;
						Il(e, Fl(e), u, o);
						break;
					default: throw Error(s(161));
				}
			} catch (t) {
				Z(e, e.return, t);
			}
			e.flags &= -3;
		}
		t & 4096 && (e.flags &= -4097);
	}
	function Mu(e) {
		if (e.subtreeFlags & 1024) for (e = e.child; e !== null;) {
			var t = e;
			Mu(t), t.tag === 5 && t.flags & 1024 && (t = t.stateNode, gh = !0, t.reset(), gh = !1), e = e.sibling;
		}
	}
	function Nu(e, t) {
		if (t.subtreeFlags & 9270) for (t = t.child; t !== null;) Pu(t, e), t = t.sibling;
		else ru(t, !1);
	}
	function Pu(e, t) {
		var n = e.alternate;
		if (n === null) Yl(e, !1);
		else switch (e.tag) {
			case 3:
				if (fu = lu = !1, Ul(), Nu(t, e), !lu && !du) {
					if (e = Hl, e !== null) for (var r = 0; r < e.length; r += 3) {
						n = e[r];
						var i = e[r + 1];
						Ep(n, e[r + 2]), n = n.ownerDocument.documentElement, n !== null && n.animate({
							opacity: [0, 0],
							pointerEvents: ["none", "none"]
						}, {
							duration: 0,
							fill: "forwards",
							pseudoElement: "::view-transition-group(" + i + ")"
						});
					}
					e = t.containerInfo, e = e.nodeType === 9 ? e.documentElement : e.ownerDocument.documentElement, e !== null && e.style.viewTransitionName === "" && (e.style.viewTransitionName = "none", e.animate({
						opacity: [0, 0],
						pointerEvents: ["none", "none"]
					}, {
						duration: 0,
						fill: "forwards",
						pseudoElement: "::view-transition-group(root)"
					}), e.animate({
						width: [0, 0],
						height: [0, 0]
					}, {
						duration: 0,
						fill: "forwards",
						pseudoElement: "::view-transition"
					})), fu = !0;
				}
				Hl = null;
				break;
			case 5:
				Nu(t, e);
				break;
			case 4:
				r = lu, lu = !1, Nu(t, e), lu && (du = !0), lu = r;
				break;
			case 22:
				e.memoizedState === null && (n.memoizedState === null ? Nu(t, e) : Yl(e, !1));
				break;
			case 30:
				r = lu, i = Ul(), lu = !1, Nu(t, e), lu && (e.flags |= 4);
				var a = e.memoizedProps, o = e.stateNode;
				t = _i(a, o), o = _i(n.memoizedProps, o);
				var s = yi(a.default, a.update);
				s === "none" ? t = !1 : (a = n.memoizedState, n.memoizedState = null, n = e.child, Wl = 0, t = nu(e, n, t, o, s, a, !0), Wl !== (a === null ? 0 : a.length) && (e.flags |= 32)), e.flags & 4 && t ? (Nd(e, e.memoizedProps.onUpdate), Hl = i) : i !== null && (i.push.apply(i, Hl), Hl = i), lu = e.flags & 32 ? !0 : r;
				break;
			default: Nu(t, e);
		}
	}
	function Fu(e, t) {
		if (t.subtreeFlags & 8772) for (t = t.child; t !== null;) hu(e, t.alternate, t), t = t.sibling;
	}
	function Iu(e, t) {
		for (e = e.child; e !== null;) {
			var n = e, r = t;
			switch (n.tag) {
				case 0:
				case 11:
				case 14:
				case 15:
					Sl(4, n, n.return), Iu(n, r);
					break;
				case 1:
					El(n, n.return);
					var i = n.stateNode;
					typeof i.componentWillUnmount == "function" && wl(n, n.return, i), Iu(n, r);
					break;
				case 27: r & 2 && gm(n.stateNode, n.type, n.memoizedProps);
				case 5:
					El(n, n.return), n.tag !== 5 && n.tag !== 27 || kl(n), Iu(n, r);
					break;
				case 6:
					kl(n);
					break;
				case 26:
					El(n, n.return), i = n.stateNode, n.memoizedState !== null || i === null || G || i.parentNode.removeChild(i), Iu(n, r);
					break;
				case 22:
					n.memoizedState === null && Iu(n, r);
					break;
				case 30:
					El(n, n.return), Iu(n, r);
					break;
				case 7: El(n, n.return);
				default: Iu(n, r);
			}
			e = e.sibling;
		}
	}
	function Lu(e, t, n) {
		for (n = t.subtreeFlags & 8772 ? n : n & -2, t = t.child; t !== null;) {
			var r = t.alternate, i = e, a = t, o = a.flags, s = !!(n & 1);
			switch (a.tag) {
				case 0:
				case 11:
				case 15:
					Lu(i, a, n), xl(4, a);
					break;
				case 1:
					if (Lu(i, a, n), r = a, i = r.stateNode, typeof i.componentDidMount == "function") try {
						i.componentDidMount();
					} catch (e) {
						Z(r, r.return, e);
					}
					if (r = a, i = r.updateQueue, i !== null) {
						var c = r.stateNode;
						try {
							var l = i.shared.hiddenCallbacks;
							if (l !== null) for (i.shared.hiddenCallbacks = null, i = 0; i < l.length; i++) Co(l[i], c);
						} catch (e) {
							Z(r, r.return, e);
						}
					}
					s && o & 64 && Cl(a), Tl(a, a.return);
					break;
				case 27: n & 2 && Rl(a);
				case 5:
					a.tag !== 5 && a.tag !== 27 || Ol(a), Lu(i, a, n), s && r === null && o & 4 && Ml(a), Tl(a, a.return);
					break;
				case 6:
					Ol(a);
					break;
				case 26:
					c = a.stateNode, a.memoizedState !== null || c === null || iu || Km(bm(c.ownerDocument), a.type, c), Lu(i, a, n), s && r === null && o & 4 && Ml(a), Tl(a, a.return);
					break;
				case 12:
					Lu(i, a, n);
					break;
				case 31:
					Lu(i, a, n), s && o & 4 && wu(i, a);
					break;
				case 13:
					Lu(i, a, n), s && o & 4 && Tu(i, a);
					break;
				case 22:
					a.memoizedState === null && Lu(i, a, n), Tl(a, a.return);
					break;
				case 30:
					Lu(i, a, n), Tl(a, a.return);
					break;
				case 7: Tl(a, a.return);
				default: Lu(i, a, n);
			}
			t = t.sibling;
		}
	}
	function Ru(e, t) {
		var n = null;
		e !== null && e.memoizedState !== null && e.memoizedState.cachePool !== null && (n = e.memoizedState.cachePool.pool), e = null, t.memoizedState !== null && t.memoizedState.cachePool !== null && (e = t.memoizedState.cachePool.pool), e !== n && (e != null && e.refCount++, n != null && Ma(n));
	}
	function zu(e, t) {
		e = null, t.alternate !== null && (e = t.alternate.memoizedState.cache), t = t.memoizedState.cache, t !== e && (t.refCount++, e != null && Ma(e));
	}
	function Bu(e, t, n, r) {
		var i = (n & 335544064) === n;
		if (t.subtreeFlags & (i ? 10262 : 10256)) for (t = t.child; t !== null;) Vu(e, t, n, r), t = t.sibling;
		else i && tu(t);
	}
	function Vu(e, t, n, r) {
		var i = (n & 335544064) === n;
		i && t.alternate === null && t.return !== null && t.return.alternate !== null && eu(t);
		var a = t.flags;
		switch (t.tag) {
			case 0:
			case 11:
			case 15:
				Bu(e, t, n, r), a & 2048 && xl(9, t);
				break;
			case 1:
				Bu(e, t, n, r);
				break;
			case 3:
				Bu(e, t, n, r), i && fu && (e = e.containerInfo, e = e.nodeType === 9 ? e.body : e.nodeName === "HTML" ? e.ownerDocument.body : e, e.style.viewTransitionName === "root" && (e.style.viewTransitionName = ""), e = e.ownerDocument.documentElement, e !== null && e.style.viewTransitionName === "none" && (e.style.viewTransitionName = "")), a & 2048 && (a = null, t.alternate !== null && (a = t.alternate.memoizedState.cache), t = t.memoizedState.cache, t !== a && (t.refCount++, a != null && Ma(a)));
				break;
			case 12:
				if (a & 2048) {
					Bu(e, t, n, r), a = t.stateNode;
					try {
						var o = t.memoizedProps, s = o.id, c = o.onPostCommit;
						typeof c == "function" && c(s, t.alternate === null ? "mount" : "update", a.passiveEffectDuration, -0);
					} catch (e) {
						Z(t, t.return, e);
					}
				} else Bu(e, t, n, r);
				break;
			case 31:
				Bu(e, t, n, r);
				break;
			case 13:
				Bu(e, t, n, r);
				break;
			case 23: break;
			case 22:
				o = t.stateNode, s = t.alternate, t.memoizedState === null ? (i && s !== null && s.memoizedState !== null && eu(t), o._visibility & 2 ? Bu(e, t, n, r) : (o._visibility |= 2, Hu(e, t, n, r, !!(t.subtreeFlags & 10256) || !1))) : (i && s !== null && s.memoizedState === null && eu(s), o._visibility & 2 ? Bu(e, t, n, r) : Uu(e, t)), a & 2048 && Ru(s, t);
				break;
			case 24:
				Bu(e, t, n, r), a & 2048 && zu(t.alternate, t);
				break;
			case 30:
				i && (a = t.alternate, a !== null && (ql(a.child, !0), ql(t.child, !0))), Bu(e, t, n, r);
				break;
			default: Bu(e, t, n, r);
		}
	}
	function Hu(e, t, n, r, i) {
		for (i &&= !!(t.subtreeFlags & 10256) || !1, t = t.child; t !== null;) {
			var a = e, o = t, s = n, c = r, l = o.flags;
			switch (o.tag) {
				case 0:
				case 11:
				case 15:
					Hu(a, o, s, c, i), xl(8, o);
					break;
				case 23: break;
				case 22:
					var u = o.stateNode;
					o.memoizedState === null ? (u._visibility |= 2, Hu(a, o, s, c, i)) : u._visibility & 2 ? Hu(a, o, s, c, i) : Uu(a, o), i && l & 2048 && Ru(o.alternate, o);
					break;
				case 24:
					Hu(a, o, s, c, i), i && l & 2048 && zu(o.alternate, o);
					break;
				default: Hu(a, o, s, c, i);
			}
			t = t.sibling;
		}
	}
	function Uu(e, t) {
		if (t.subtreeFlags & 10256) for (t = t.child; t !== null;) {
			var n = e, r = t, i = r.flags;
			switch (r.tag) {
				case 22:
					Uu(n, r), i & 2048 && Ru(r.alternate, r);
					break;
				case 24:
					Uu(n, r), i & 2048 && zu(r.alternate, r);
					break;
				default: Uu(n, r);
			}
			t = t.sibling;
		}
	}
	var Wu = 8192;
	function Gu(e, t, n) {
		if (e.subtreeFlags & Wu) for (e = e.child; e !== null;) Ku(e, t, n), e = e.sibling;
	}
	function Ku(e, t, n) {
		switch (e.tag) {
			case 26:
				Gu(e, t, n), e.flags & Wu && (e.memoizedState === null ? (e = e.stateNode, (t & 335544128) === t && Zm(n, e)) : Qm(n, ku, e.memoizedState, e.memoizedProps));
				break;
			case 5:
				Gu(e, t, n), e.flags & Wu && (e = e.stateNode, (t & 335544128) === t && Zm(n, e));
				break;
			case 3:
			case 4:
				var r = ku;
				ku = bm(e.stateNode.containerInfo), Gu(e, t, n), ku = r;
				break;
			case 22:
				e.memoizedState === null && (r = e.alternate, r !== null && r.memoizedState !== null ? (r = Wu, Wu = 16777216, Gu(e, t, n), Wu = r) : Gu(e, t, n));
				break;
			case 30:
				if ((e.flags & Wu) !== 0 && (r = e.memoizedProps.name, r != null && r !== "auto")) {
					var i = e.stateNode;
					i.paired = null, Bl === null && (Bl = /* @__PURE__ */ new Map()), Bl.set(r, i);
				}
				Gu(e, t, n);
				break;
			default: Gu(e, t, n);
		}
	}
	function qu(e) {
		var t = e.alternate;
		if (t !== null && (e = t.child, e !== null)) {
			t.child = null;
			do
				t = e.sibling, e.sibling = null, e = t;
			while (e !== null);
		}
	}
	function Ju(e) {
		var t = e.deletions;
		if (e.flags & 16) {
			if (t !== null) for (var n = 0; n < t.length; n++) {
				var r = t[n];
				cu = r, Zu(r, e);
			}
			qu(e);
		}
		if (e.subtreeFlags & 10256) for (e = e.child; e !== null;) Yu(e), e = e.sibling;
	}
	function Yu(e) {
		switch (e.tag) {
			case 0:
			case 11:
			case 15:
				Ju(e), e.flags & 2048 && Sl(9, e, e.return);
				break;
			case 3:
				Ju(e);
				break;
			case 12:
				Ju(e);
				break;
			case 22:
				var t = e.stateNode;
				e.memoizedState !== null && t._visibility & 2 && (e.return === null || e.return.tag !== 13) ? (t._visibility &= -3, Xu(e)) : Ju(e);
				break;
			default: Ju(e);
		}
	}
	function Xu(e) {
		var t = e.deletions;
		if (e.flags & 16) {
			if (t !== null) for (var n = 0; n < t.length; n++) {
				var r = t[n];
				cu = r, Zu(r, e);
			}
			qu(e);
		}
		for (e = e.child; e !== null;) {
			switch (t = e, t.tag) {
				case 0:
				case 11:
				case 15:
					Sl(8, t, t.return), Xu(t);
					break;
				case 22:
					n = t.stateNode, n._visibility & 2 && (n._visibility &= -3, Xu(t));
					break;
				default: Xu(t);
			}
			e = e.sibling;
		}
	}
	function Zu(e, t) {
		for (; cu !== null;) {
			var n = cu;
			switch (n.tag) {
				case 0:
				case 11:
				case 15:
					Sl(8, n, t);
					break;
				case 23:
				case 22:
					if (n.memoizedState !== null && n.memoizedState.cachePool !== null) {
						var r = n.memoizedState.cachePool.pool;
						r != null && r.refCount++;
					}
					break;
				case 24: Ma(n.memoizedState.cache);
			}
			if (r = n.child, r !== null) r.return = n, cu = r;
			else a: for (n = e; cu !== null;) {
				r = cu;
				var i = r.sibling, a = r.return;
				if (yu(r), r === n) {
					cu = null;
					break a;
				}
				if (i !== null) {
					i.return = a, cu = i;
					break a;
				}
				cu = a;
			}
		}
	}
	var Qu = {
		getCacheForType: function(e) {
			var t = wa(Aa), n = t.data.get(e);
			return n === void 0 && (n = e(), t.data.set(e, n)), n;
		},
		cacheSignal: function() {
			return wa(Aa).controller.signal;
		}
	}, $u = typeof WeakMap == "function" ? WeakMap : Map, K = 0, q = null, J = null, Y = 0, X = 0, ed = null, td = !1, nd = !1, rd = !1, id = 0, ad = 0, od = 0, sd = 0, cd = 0, ld = 0, ud = 0, dd = null, fd = null, pd = !1, md = 0, hd = 0, gd = Infinity, _d = null, vd = null, yd = 0, bd = null, xd = null, Sd = 0, Cd = 0, wd = null, Td = null, Ed = null, Dd = null, Od = null, kd = 0, Ad = null;
	function jd() {
		return K & 2 && Y !== 0 ? Y & -Y : k.T === null ? Ct() : Pf();
	}
	function Md() {
		if (ld === 0) {
			if (!(Y & 536870912) || V) {
				var e = st;
				st <<= 1, !(st & 3932160) && (st = 262144), ld = e;
			} else ld = 536870912;
		}
		return e = Ao.current, e !== null && (e.flags |= 32), ld;
	}
	function Nd(e, t) {
		if (t != null) {
			var n = e.stateNode, r = n.ref;
			r === null && (r = n.ref = Pp(_i(e.memoizedProps, n))), Dd === null && (Dd = []), Dd.push(t.bind(null, r));
		}
	}
	function Pd(e, t, n) {
		(e === q && (X === 2 || X === 9) || e.cancelPendingCommit !== null) && (Vd(e, 0), Rd(e, Y, ld, !1)), gt(e, n), K & 2 && e === q || (e === q && (!(K & 2) && (sd |= n), ad === 4 && Rd(e, Y, ld, !1)), Ef(e));
	}
	function Fd(e, t, n) {
		if (K & 6) throw Error(s(327));
		var r = !n && !(t & 127) && (t & e.expiredLanes) === 0 || dt(e, t), i = r ? Yd(e, t) : qd(e, t, !0), a = r;
		do {
			if (i === 0) {
				nd && !r && Rd(e, t, 0, !1);
				break;
			}
			if (n = e.current.alternate, a && !Ld(n)) i = qd(e, t, !1), a = !1;
			else {
				if (i === 2) {
					if (a = t, e.errorRecoveryDisabledLanes & a) var o = 0;
					else o = e.pendingLanes & -536870913, o = o === 0 ? o & 536870912 ? 536870912 : 0 : o;
					if (o !== 0) {
						t = o;
						a: {
							var c = e;
							i = dd;
							var l = c.current.memoizedState.isDehydrated;
							if (l && (Vd(c, o).flags |= 256), o = qd(c, o, !1), o !== 2 && o !== 6) {
								if (rd && !l) {
									c.errorRecoveryDisabledLanes |= a, sd |= a, i = 4;
									break a;
								}
								a = fd, fd = i, a !== null && (fd === null ? fd = a : fd.push.apply(fd, a));
							}
							i = o;
						}
						if (a = !1, i !== 2) continue;
					}
				}
				if (i === 1) {
					Vd(e, 0), Rd(e, t, 0, !0);
					break;
				}
				a: {
					switch (r = e, a = i, a) {
						case 0:
						case 1: throw Error(s(345));
						case 4: if ((t & 4194048) !== t && (t & 62914560) !== t) break;
						case 6:
							Rd(r, t, ld, !td);
							break a;
						case 2:
							fd = null;
							break;
						case 3:
						case 5: break;
						default: throw Error(s(329));
					}
					if ((t & 62914560) === t && (i = md + 300 - P(), 10 < i)) {
						if (Rd(r, t, ld, !td), ut(r, 0, !0) !== 0) break a;
						Sd = t, r.timeoutHandle = gp(Id.bind(null, r, n, fd, _d, pd, t, ld, sd, ud, td, a, "Throttled", -0, 0), i);
						break a;
					}
					Id(r, n, fd, _d, pd, t, ld, sd, ud, td, a, null, -0, 0);
				}
				break;
			}
		} while (1);
		Ef(e);
	}
	function Id(e, t, n, r, i, a, o, s, c, l, u, d, f, p) {
		e.timeoutHandle = -1;
		var m = t.subtreeFlags, h = (a & 335544064) === a;
		d = null, (h || m & 8192 || (m & 16785408) == 16785408) && (d = {
			stylesheets: null,
			count: 0,
			imgCount: 0,
			imgBytes: 0,
			suspenseyImages: [],
			waitingForImages: !0,
			waitingForViewTransition: !1,
			unsuspend: vn
		}, Bl = null, Ku(t, a, d), h && (m = d, h = e.containerInfo, h = (h.nodeType === 9 ? h : h.ownerDocument).__reactViewTransition, h != null && (m.count++, m.waitingForViewTransition = !0, m = nh.bind(m), h.finished.then(m, m))), m = (a & 62914560) === a ? md - P() : (a & 4194048) === a ? hd - P() : 0, m = eh(d, m), m !== null) ? (Sd = a, e.cancelPendingCommit = m(nf.bind(null, e, t, a, n, r, i, o, s, c, l, u, d, null, f, p)), Rd(e, a, o, !l)) : nf(e, t, a, n, r, i, o, s, c, l, u, d);
	}
	function Ld(e) {
		for (var t = e;;) {
			var n = t.tag;
			if ((n === 0 || n === 11 || n === 15) && t.flags & 16384 && (n = t.updateQueue, n !== null && (n = n.stores, n !== null))) for (var r = 0; r < n.length; r++) {
				var i = n[r], a = i.getSnapshot;
				i = i.value;
				try {
					if (!Vr(a(), i)) return !1;
				} catch {
					return !1;
				}
			}
			if (n = t.child, t.subtreeFlags & 16384 && n !== null) n.return = t, t = n;
			else {
				if (t === e) break;
				for (; t.sibling === null;) {
					if (t.return === null || t.return === e) return !0;
					t = t.return;
				}
				t.sibling.return = t.return, t = t.sibling;
			}
		}
		return !0;
	}
	function Rd(e, t, n, r) {
		t = ft(e, t), t &= ~cd, t &= ~sd, e.suspendedLanes |= t, e.pingedLanes &= ~t, r && (e.warmLanes |= t), r = e.expirationTimes;
		for (var i = t; 0 < i;) {
			var a = 31 - nt(i), o = 1 << a;
			r[a] = -1, i &= ~o;
		}
		n !== 0 && vt(e, n, t);
	}
	function zd() {
		return K & 6 ? !0 : (Df(0, !1), !1);
	}
	function Bd() {
		if (J !== null) {
			if (X === 0) var e = J.return;
			else e = J, ga = ha = null, is(e), io = null, ao = 0, e = J;
			for (; e !== null;) bl(e.alternate, e), e = e.return;
			J = null;
		}
	}
	function Vd(e, t) {
		var n = e.timeoutHandle;
		return n !== -1 && (e.timeoutHandle = -1, _p(n)), n = e.cancelPendingCommit, n !== null && (e.cancelPendingCommit = null, n()), Sd = 0, Bd(), q = e, J = n = Pi(e.current, null), Y = t, X = 0, ed = null, td = !1, nd = dt(e, t), rd = !1, ud = ld = cd = sd = od = ad = 0, fd = dd = null, pd = !1, id = ft(e, t), wi(), n;
	}
	function Hd(e, t) {
		H = null, k.H = mc, t === Ja || t === Xa ? (t = no(), X = 3) : t === Ya ? (t = no(), X = 4) : X = t === Mc ? 8 : typeof t == "object" && t && typeof t.then == "function" ? 6 : 1, ed = t, J === null && (ad = 1, Ec(e, Hi(t, e.current)));
	}
	function Ud() {
		var e = Ao.current;
		return e === null ? !0 : (Y & 4194048) === Y ? jo === null : (Y & 62914560) === Y || Y & 536870912 ? e === jo : !1;
	}
	function Wd() {
		var e = k.H;
		return k.H = mc, e === null ? mc : e;
	}
	function Gd() {
		var e = k.A;
		return k.A = Qu, e;
	}
	function Kd() {
		ad = 4, td || (Y & 4194048) !== Y && Ao.current !== null || (nd = !0), !(od & 134217727) && !(sd & 134217727) || q === null || Rd(q, Y, ld, !1);
	}
	function qd(e, t, n) {
		var r = K;
		K |= 2;
		var i = Wd(), a = Gd();
		(q !== e || Y !== t) && (_d = null, Vd(e, t)), t = !1;
		var o = ad;
		a: do
			try {
				if (X !== 0 && J !== null) {
					var s = J, c = ed;
					switch (X) {
						case 8:
							Bd(), o = 6;
							break a;
						case 3:
						case 2:
						case 9:
						case 6:
							Ao.current === null && (t = !0);
							var l = X;
							if (X = 0, ed = null, $d(e, s, c, l), n && nd) {
								o = 0;
								break a;
							}
							break;
						default: l = X, X = 0, ed = null, $d(e, s, c, l);
					}
				}
				Jd(), o = ad;
				break;
			} catch (t) {
				Hd(e, t);
			}
		while (1);
		return t && e.shellSuspendCounter++, ga = ha = null, K = r, k.H = i, k.A = a, J === null && (q = null, Y = 0, wi()), o;
	}
	function Jd() {
		for (; J !== null;) Zd(J);
	}
	function Yd(e, t) {
		var n = K;
		K |= 2;
		var r = Wd(), i = Gd();
		q !== e || Y !== t ? (_d = null, gd = P() + 500, Vd(e, t)) : nd = dt(e, t);
		a: do
			try {
				if (X !== 0 && J !== null) {
					t = J;
					var a = ed;
					b: switch (X) {
						case 1:
							X = 0, ed = null, $d(e, t, a, 1);
							break;
						case 2:
						case 9:
							if (Qa(a)) {
								X = 0, ed = null, Qd(t);
								break;
							}
							t = function() {
								X !== 2 && X !== 9 || q !== e || (X = 7), Ef(e);
							}, a.then(t, t);
							break a;
						case 3:
							X = 7;
							break a;
						case 4:
							X = 5;
							break a;
						case 7:
							Qa(a) ? (X = 0, ed = null, Qd(t)) : (X = 0, ed = null, $d(e, t, a, 7));
							break;
						case 5:
							var o = null;
							switch (J.tag) {
								case 26: o = J.memoizedState;
								case 5:
								case 27:
									var c = J;
									if (o ? Ym(o) : c.stateNode.complete) {
										X = 0, ed = null;
										var l = c.sibling;
										if (l !== null) J = l;
										else {
											var u = c.return;
											u === null ? J = null : (J = u, ef(u));
										}
										break b;
									}
							}
							X = 0, ed = null, $d(e, t, a, 5);
							break;
						case 6:
							X = 0, ed = null, $d(e, t, a, 6);
							break;
						case 8:
							Bd(), ad = 6;
							break a;
						default: throw Error(s(462));
					}
				}
				Xd();
				break;
			} catch (t) {
				Hd(e, t);
			}
		while (1);
		return ga = ha = null, k.H = r, k.A = i, K = n, J === null ? (q = null, Y = 0, wi(), ad) : 0;
	}
	function Xd() {
		for (; J !== null && !Ue();) Zd(J);
	}
	function Zd(e) {
		var t = fl(e.alternate, e, id);
		e.memoizedProps = e.pendingProps, t === null ? ef(e) : J = t;
	}
	function Qd(e) {
		var t = e, n = t.alternate;
		switch (t.tag) {
			case 15:
			case 0:
				t = Kc(n, t, t.pendingProps, t.type, void 0, Y);
				break;
			case 11:
				t = Kc(n, t, t.pendingProps, t.type.render, t.ref, Y);
				break;
			case 5:
				is(t);
				var r = t;
				r === ra && (V ? (la(r), r.tag === 5 && r.stateNode != null && (B = r.stateNode)) : (la(r), V = !0));
			default: bl(n, t), t = J = Fi(t, id), t = fl(n, t, id);
		}
		e.memoizedProps = e.pendingProps, t === null ? ef(e) : J = t;
	}
	function $d(e, t, n, r) {
		ga = ha = null, is(t), io = null, ao = 0;
		var i = t.return;
		try {
			if (jc(e, i, t, n, Y)) {
				ad = 1, Ec(e, Hi(n, e.current)), J = null;
				return;
			}
		} catch (t) {
			if (i !== null) throw J = i, t;
			ad = 1, Ec(e, Hi(n, e.current)), J = null;
			return;
		}
		t.flags & 32768 ? (V || r === 1 ? e = !0 : nd || Y & 536870912 ? e = !1 : (td = e = !0, (r === 2 || r === 9 || r === 3 || r === 6) && (r = Ao.current, r !== null && r.tag === 13 && (r.flags |= 16384))), tf(t, e)) : ef(t);
	}
	function ef(e) {
		var t = e;
		do {
			if (t.flags & 32768) {
				tf(t, td);
				return;
			}
			e = t.return;
			var n = vl(t.alternate, t, id);
			if (n !== null) {
				J = n;
				return;
			}
			if (t = t.sibling, t !== null) {
				J = t;
				return;
			}
			J = t = e;
		} while (t !== null);
		ad === 0 && (ad = 5);
	}
	function tf(e, t) {
		do {
			var n = yl(e.alternate, e);
			if (n !== null) {
				n.flags &= 32767, J = n;
				return;
			}
			if (n = e.return, n !== null && (n.flags |= 32768, n.subtreeFlags = 0, n.deletions = null), !t && (e = e.sibling, e !== null)) {
				J = e;
				return;
			}
			J = e = n;
		} while (e !== null);
		ad = 6, J = null;
	}
	function nf(e, t, n, r, i, a, o, c, l, u, d, f) {
		e.cancelPendingCommit = null;
		do
			df();
		while (yd !== 0);
		if (K & 6) throw Error(s(327));
		if (t !== null) {
			if (t === e.current) throw Error(s(177));
			e === q && (J = q = null, Y = 0), xd = t, bd = e, Sd = n, wd = i, Td = r, rf(e, t, n, o, c, l, f);
		}
	}
	function rf(e, t, n, r, i, a, o) {
		var s = t.lanes | t.childLanes;
		if (Cd = s, s |= Ci, _t(e, n, s, r, i, a), Dd = null, (n & 335544064) === n ? (Od = Fa(e), r = 10262) : (Od = null, r = 10256), (t.subtreeFlags & r) !== 0 || (t.flags & r) !== 0 ? (e.callbackNode = null, e.callbackPriority = 0, yf(Je, function() {
			return ff(), null;
		})) : (e.callbackNode = null, e.callbackPriority = 0), zl = !1, r = !!(t.flags & 13878), t.subtreeFlags & 13878 || r) {
			r = k.T, k.T = null, i = A.p, A.p = 2, a = K, K |= 4;
			try {
				pu(e, t, n);
			} finally {
				K = a, A.p = i, k.T = r;
			}
		}
		yd = 1, zl ? Ed = Mp(o, e.containerInfo, Od, sf, cf, of, lf, ff, af, null, null) : (sf(), cf(), lf());
	}
	function af(e) {
		if (yd !== 0) {
			var t = bd.onRecoverableError;
			t(e, { componentStack: null });
		}
	}
	function of() {
		yd === 3 && (yd = 0, Pu(xd, bd), yd = 4);
	}
	function sf() {
		if (yd === 1) {
			yd = 0;
			var e = bd, t = xd, n = Sd, r = !!(t.flags & 13878);
			if (t.subtreeFlags & 13878 || r) {
				r = k.T, k.T = null;
				var i = A.p;
				A.p = 2;
				var a = K;
				K |= 4;
				try {
					uu = du = !1, Au(t, e, n), n = cp;
					var o = qr(e.containerInfo), s = n.focusedElem, c = n.selectionRange;
					if (o !== s && s && s.ownerDocument && Kr(s.ownerDocument.documentElement, s)) {
						if (c !== null && Jr(s)) {
							var l = c.start, u = c.end;
							if (u === void 0 && (u = l), "selectionStart" in s) s.selectionStart = l, s.selectionEnd = Math.min(u, s.value.length);
							else {
								var d = s.ownerDocument || document, f = d && d.defaultView || window;
								if (f.getSelection) {
									var p = f.getSelection(), m = s.textContent.length, h = Math.min(c.start, m), g = c.end === void 0 ? h : Math.min(c.end, m);
									!p.extend && h > g && (o = g, g = h, h = o);
									var _ = Gr(s, h), v = Gr(s, g);
									if (_ && v && (p.rangeCount !== 1 || p.anchorNode !== _.node || p.anchorOffset !== _.offset || p.focusNode !== v.node || p.focusOffset !== v.offset)) {
										var y = d.createRange();
										y.setStart(_.node, _.offset), p.removeAllRanges(), h > g ? (p.addRange(y), p.extend(v.node, v.offset)) : (y.setEnd(v.node, v.offset), p.addRange(y));
									}
								}
							}
						}
						for (d = [], p = s; p = p.parentNode;) p.nodeType === 1 && d.push({
							element: p,
							left: p.scrollLeft,
							top: p.scrollTop
						});
						for (typeof s.focus == "function" && s.focus(), s = 0; s < d.length; s++) {
							var b = d[s];
							b.element.scrollLeft = b.left, b.element.scrollTop = b.top;
						}
					}
					gh = !!sp, cp = sp = null;
				} finally {
					K = a, A.p = i, k.T = r;
				}
			}
			e.current = t, yd = 2;
		}
	}
	function cf() {
		if (yd === 2) {
			yd = 0;
			var e = bd, t = xd, n = !!(t.flags & 8772);
			if (t.subtreeFlags & 8772 || n) {
				n = k.T, k.T = null;
				var r = A.p;
				A.p = 2;
				var i = K;
				K |= 4;
				try {
					hu(e, t.alternate, t);
				} finally {
					K = i, A.p = r, k.T = n;
				}
			}
			yd = 3;
		}
	}
	function lf() {
		if (yd === 4 || yd === 3) {
			yd = 0;
			var e = Ed;
			Ed = null, We();
			var t = bd, n = xd, r = Sd, i = Td, a = (r & 335544064) === r ? 10262 : 10256;
			if ((n.subtreeFlags & a) !== 0 || (n.flags & a) !== 0 ? yd = 5 : (yd = 0, xd = bd = null, uf(t, t.pendingLanes)), a = t.pendingLanes, a === 0 && (vd = null), St(r), n = n.stateNode, et && typeof et.onCommitFiberRoot == "function") try {
				et.onCommitFiberRoot($e, n, void 0, (n.current.flags & 128) == 128);
			} catch {}
			if (i !== null) {
				n = k.T, a = A.p, A.p = 2, k.T = null;
				try {
					for (var o = t.onRecoverableError, s = 0; s < i.length; s++) {
						var c = i[s];
						o(c.value, { componentStack: c.stack });
					}
				} finally {
					k.T = n, A.p = a;
				}
			}
			if (i = Dd, o = Od, Od = null, i !== null && (Dd = null, o === null && (o = []), e !== null)) for (c = 0; c < i.length; c++) n = (0, i[c])(o), n !== void 0 && e.finished.finally(n);
			Sd & 3 && df(), Ef(t), a = t.pendingLanes, r & 261930 && a & 42 ? t === Ad ? kd++ : (kd = 0, Ad = t) : (kd = 0, Ad = null), Df(0, !1);
		}
	}
	function uf(e, t) {
		(e.pooledCacheLanes &= t) === 0 && (t = e.pooledCache, t != null && (e.pooledCache = null, Ma(t)));
	}
	function df() {
		return Ed !== null && (Ed.skipTransition(), Ed = null), sf(), cf(), lf(), ff();
	}
	function ff() {
		if (yd !== 5) return !1;
		var e = bd, t = Cd;
		Cd = 0;
		var n = St(Sd), r = k.T, i = A.p;
		try {
			A.p = 32 > n ? 32 : n, k.T = null, n = wd, wd = null;
			var a = bd, o = Sd;
			if (yd = 0, xd = bd = null, Sd = 0, K & 6) throw Error(s(331));
			var c = K;
			if (K |= 4, Yu(a.current), Vu(a, a.current, o, n), K = c, Df(0, !1), et && typeof et.onPostCommitFiberRoot == "function") try {
				et.onPostCommitFiberRoot($e, a);
			} catch {}
			return !0;
		} finally {
			A.p = i, k.T = r, uf(e, t);
		}
	}
	function pf(e, t, n) {
		t = Hi(n, t), t = Oc(e.stateNode, t, 2), e = _o(e, t, 2), e !== null && (gt(e, 2), Ef(e));
	}
	function Z(e, t, n) {
		if (e.tag === 3) pf(e, e, n);
		else for (; t !== null;) {
			if (t.tag === 3) {
				pf(t, e, n);
				break;
			}
			if (t.tag === 1) {
				var r = t.stateNode;
				if (typeof t.type.getDerivedStateFromError == "function" || typeof r.componentDidCatch == "function" && (vd === null || !vd.has(r))) {
					e = Hi(n, e), n = kc(2), r = _o(t, n, 2), r !== null && (Ac(n, r, t, e), gt(r, 2), Ef(r));
					break;
				}
			}
			t = t.return;
		}
	}
	function mf(e, t, n) {
		var r = e.pingCache;
		if (r === null) {
			r = e.pingCache = new $u();
			var i = /* @__PURE__ */ new Set();
			r.set(t, i);
		} else i = r.get(t), i === void 0 && (i = /* @__PURE__ */ new Set(), r.set(t, i));
		i.has(n) || (rd = !0, i.add(n), e = hf.bind(null, e, t, n), t.then(e, e));
	}
	function hf(e, t, n) {
		var r = e.pingCache;
		r !== null && r.delete(t), e.pingedLanes |= e.suspendedLanes & n, e.warmLanes &= ~n, q === e && (Y & n) === n && (ad === 4 || ad === 3 && (Y & 62914560) === Y && 300 > P() - md ? K & 2 ? cd |= n : Vd(e, 0) : cd |= n, ud === Y && (ud = 0)), Ef(e);
	}
	function gf(e, t) {
		t === 0 && (t = mt()), e = Di(e, t), e !== null && (gt(e, t), Ef(e));
	}
	function _f(e) {
		var t = e.memoizedState, n = 0;
		t !== null && (n = t.retryLane), gf(e, n);
	}
	function vf(e, t) {
		var n = 0;
		switch (e.tag) {
			case 31:
			case 13:
				var r = e.stateNode, i = e.memoizedState;
				i !== null && (n = i.retryLane);
				break;
			case 19:
				r = e.stateNode;
				break;
			case 22:
				r = e.stateNode._retryCache;
				break;
			default: throw Error(s(314));
		}
		r !== null && r.delete(t), gf(e, n);
	}
	function yf(e, t) {
		return Ve(e, t);
	}
	var bf = null, xf = null, Sf = !1, Cf = !1, wf = !1, Tf = 0;
	function Ef(e) {
		e !== xf && e.next === null && (xf === null ? bf = xf = e : xf = xf.next = e), Cf = !0, Sf || (Sf = !0, Nf());
	}
	function Df(e, t) {
		if (!wf && Cf) {
			wf = !0;
			do
				for (var n = !1, r = bf; r !== null;) {
					if (!t) {
						if (e !== 0) {
							var i = r.pendingLanes;
							if (i === 0) var a = 0;
							else {
								var o = r.suspendedLanes, s = r.pingedLanes;
								a = (1 << 31 - nt(42 | e) + 1) - 1, a &= i & ~(o & ~s), a = a & 201326741 ? a & 201326741 | 1 : a ? a | 2 : 0;
							}
							a !== 0 && (n = !0, Mf(r, a));
						} else a = Y, a = ut(r, r === q ? a : 0, r.cancelPendingCommit !== null || r.timeoutHandle !== -1), !(a & 3) || dt(r, a) || (n = !0, Mf(r, a));
					}
					r = r.next;
				}
			while (n);
			wf = !1;
		}
	}
	function Of() {
		kf();
	}
	function kf() {
		Cf = Sf = !1;
		var e = 0;
		Tf !== 0 && hp() && (e = Tf);
		for (var t = P(), n = null, r = bf; r !== null;) {
			var i = r.next, a = Af(r, t);
			a === 0 ? (r.next = null, n === null ? bf = i : n.next = i, i === null && (xf = n)) : (n = r, (e !== 0 || a & 3) && (Cf = !0)), r = i;
		}
		yd !== 0 && yd !== 5 || Df(e, !1), Tf !== 0 && (Tf = 0);
	}
	function Af(e, t) {
		for (var n = e.suspendedLanes, r = e.pingedLanes, i = e.expirationTimes, a = e.pendingLanes & -62914561; 0 < a;) {
			var o = 31 - nt(a), s = 1 << o, c = i[o];
			c === -1 ? ((s & n) === 0 || (s & r) !== 0) && (i[o] = pt(s, t)) : c <= t && (e.expiredLanes |= s), a &= ~s;
		}
		if (t = q, n = Y, n = ut(e, e === t ? n : 0, e.cancelPendingCommit !== null || e.timeoutHandle !== -1), r = e.callbackNode, n === 0 || e === t && (X === 2 || X === 9) || e.cancelPendingCommit !== null) return r !== null && r !== null && He(r), e.callbackNode = null, e.callbackPriority = 0;
		if (!(n & 3) || dt(e, n)) {
			if (t = n & -n, t === e.callbackPriority) return t;
			switch (r !== null && He(r), St(n)) {
				case 2:
				case 8:
					n = qe;
					break;
				case 32:
					n = Je;
					break;
				case 268435456:
					n = Xe;
					break;
				default: n = Je;
			}
			return r = jf.bind(null, e), n = Ve(n, r), e.callbackPriority = t, e.callbackNode = n, t;
		}
		return r !== null && r !== null && He(r), e.callbackPriority = 2, e.callbackNode = null, 2;
	}
	function jf(e, t) {
		if (yd !== 0 && yd !== 5) return e.callbackNode = null, e.callbackPriority = 0, null;
		var n = e.callbackNode;
		if (df() && e.callbackNode !== n) return null;
		var r = Y;
		return r = ut(e, e === q ? r : 0, e.cancelPendingCommit !== null || e.timeoutHandle !== -1), r === 0 ? null : (Fd(e, r, t), Af(e, P()), e.callbackNode != null && e.callbackNode === n ? jf.bind(null, e) : null);
	}
	function Mf(e, t) {
		if (df()) return null;
		Fd(e, t, !0);
	}
	function Nf() {
		bp(function() {
			K & 6 ? Ve(Ke, Of) : kf();
		});
	}
	function Pf() {
		if (Tf === 0) {
			var e = Ra;
			e === 0 && (e = ot, ot <<= 1, !(ot & 261888) && (ot = 256)), Tf = e;
		}
		return Tf;
	}
	function Ff(e) {
		return e == null || typeof e == "symbol" || typeof e == "boolean" ? null : typeof e == "function" ? e : _n(e);
	}
	function If(e, t, n, r, i) {
		if (t === "submit" && n && n.stateNode === i) {
			var a = Ff((i[Dt] || null).action), o = r.submitter;
			o && (t = (t = o[Dt] || null) ? Ff(t.formAction) : o.getAttribute("formAction"), t !== null && (a = t, o = null));
			var s = new zn("action", "action", null, r, i);
			e.push({
				event: s,
				listeners: [{
					instance: null,
					listener: function() {
						if (r.defaultPrevented) {
							if (Tf !== 0) {
								var e = new FormData(i, o);
								ec(n, {
									pending: !0,
									data: e,
									method: i.method,
									action: a
								}, null, e);
							}
						} else typeof a == "function" && (s.preventDefault(), e = new FormData(i, o), ec(n, {
							pending: !0,
							data: e,
							method: i.method,
							action: a
						}, a, e));
					},
					currentTarget: i
				}]
			});
		}
	}
	for (var Lf = 0; Lf < mi.length; Lf++) {
		var Rf = mi[Lf];
		hi(Rf.toLowerCase(), "on" + (Rf[0].toUpperCase() + Rf.slice(1)));
	}
	hi(oi, "onAnimationEnd"), hi(si, "onAnimationIteration"), hi(ci, "onAnimationStart"), hi("dblclick", "onDoubleClick"), hi("focusin", "onFocus"), hi("focusout", "onBlur"), hi(li, "onTransitionRun"), hi(ui, "onTransitionStart"), hi(di, "onTransitionCancel"), hi(fi, "onTransitionEnd"), Vt("onMouseEnter", ["mouseout", "mouseover"]), Vt("onMouseLeave", ["mouseout", "mouseover"]), Vt("onPointerEnter", ["pointerout", "pointerover"]), Vt("onPointerLeave", ["pointerout", "pointerover"]), Bt("onChange", "change click focusin focusout input keydown keyup selectionchange".split(" ")), Bt("onSelect", "focusout contextmenu dragend focusin keydown keyup mousedown mouseup selectionchange".split(" ")), Bt("onBeforeInput", [
		"compositionend",
		"keypress",
		"textInput",
		"paste"
	]), Bt("onCompositionEnd", "compositionend focusout keydown keypress keyup mousedown".split(" ")), Bt("onCompositionStart", "compositionstart focusout keydown keypress keyup mousedown".split(" ")), Bt("onCompositionUpdate", "compositionupdate focusout keydown keypress keyup mousedown".split(" "));
	var zf = "abort canplay canplaythrough durationchange emptied encrypted ended error loadeddata loadedmetadata loadstart pause play playing progress ratechange resize seeked seeking stalled suspend timeupdate volumechange waiting".split(" "), Bf = new Set("beforetoggle cancel close invalid load scroll scrollend toggle".split(" ").concat(zf));
	function Vf(e, t) {
		t = !!(t & 4);
		for (var n = 0; n < e.length; n++) {
			var r = e[n], i = r.event;
			r = r.listeners;
			a: {
				var a = void 0;
				if (t) for (var o = r.length - 1; 0 <= o; o--) {
					var s = r[o], c = s.instance, l = s.currentTarget;
					if (s = s.listener, c !== a && i.isPropagationStopped()) break a;
					a = s, i.currentTarget = l;
					try {
						a(i);
					} catch (e) {
						bi(e);
					}
					i.currentTarget = null, a = c;
				}
				else for (o = 0; o < r.length; o++) {
					if (s = r[o], c = s.instance, l = s.currentTarget, s = s.listener, c !== a && i.isPropagationStopped()) break a;
					a = s, i.currentTarget = l;
					try {
						a(i);
					} catch (e) {
						bi(e);
					}
					i.currentTarget = null, a = c;
				}
			}
		}
	}
	function Q(e, t) {
		var n = t[kt];
		n === void 0 && (n = t[kt] = /* @__PURE__ */ new Set());
		var r = e + "__bubble";
		n.has(r) || (Gf(t, e, 2, !1), n.add(r));
	}
	function Hf(e, t, n) {
		var r = 0;
		t && (r |= 4), Gf(n, e, r, t);
	}
	var Uf = "_reactListening" + Math.random().toString(36).slice(2);
	function Wf(e) {
		if (!e[Uf]) {
			e[Uf] = !0, Rt.forEach(function(t) {
				t !== "selectionchange" && (Bf.has(t) || Hf(t, !1, e), Hf(t, !0, e));
			});
			var t = e.nodeType === 9 ? e : e.ownerDocument;
			t === null || t[Uf] || (t[Uf] = !0, Hf("selectionchange", !1, t));
		}
	}
	function Gf(e, t, n, r) {
		switch (Ch(t)) {
			case 2:
				var i = _h;
				break;
			case 8:
				i = vh;
				break;
			default: i = yh;
		}
		n = i.bind(null, t, n, e), i = void 0, !On || t !== "touchstart" && t !== "touchmove" && t !== "wheel" || (i = !0), r ? i === void 0 ? e.addEventListener(t, n, !0) : e.addEventListener(t, n, {
			capture: !0,
			passive: i
		}) : i === void 0 ? e.addEventListener(t, n, !1) : e.addEventListener(t, n, { passive: i });
	}
	function Kf(e, t, n, r, i) {
		var a = r;
		if (!(t & 1) && !(t & 2) && r !== null) a: for (;;) {
			if (r === null) return;
			var o = r.tag;
			if (o === 3 || o === 4) {
				var s = r.stateNode.containerInfo;
				if (s === i) break;
				if (o === 4) for (o = r.return; o !== null;) {
					var c = o.tag;
					if ((c === 3 || c === 4) && o.stateNode.containerInfo === i) return;
					o = o.return;
				}
				for (; s !== null;) {
					if (o = F(s), o === null) return;
					if (c = o.tag, c === 5 || c === 6 || c === 26 || c === 27) {
						r = a = o;
						continue a;
					}
					s = s.parentNode;
				}
			}
			r = r.return;
		}
		Tn(function() {
			var r = a, i = bn(n), o = [];
			a: {
				var s = pi.get(e);
				if (s !== void 0) {
					var c = zn, u = e;
					switch (e) {
						case "keypress": if (Pn(n) === 0) break a;
						case "keydown":
						case "keyup":
							c = rr;
							break;
						case "focusin":
							u = "focus", c = Jn;
							break;
						case "focusout":
							u = "blur", c = Jn;
							break;
						case "beforeblur":
						case "afterblur":
							c = Jn;
							break;
						case "click": if (n.button === 2) break a;
						case "auxclick":
						case "dblclick":
						case "mousedown":
						case "mousemove":
						case "mouseup":
						case "mouseout":
						case "mouseover":
						case "contextmenu":
							c = Kn;
							break;
						case "drag":
						case "dragend":
						case "dragenter":
						case "dragexit":
						case "dragleave":
						case "dragover":
						case "dragstart":
						case "drop":
							c = qn;
							break;
						case "touchcancel":
						case "touchend":
						case "touchmove":
						case "touchstart":
							c = or;
							break;
						case oi:
						case si:
						case ci:
							c = Yn;
							break;
						case fi:
							c = sr;
							break;
						case "scroll":
						case "scrollend":
							c = Vn;
							break;
						case "wheel":
							c = cr;
							break;
						case "copy":
						case "cut":
						case "paste":
							c = Xn;
							break;
						case "gotpointercapture":
						case "lostpointercapture":
						case "pointercancel":
						case "pointerdown":
						case "pointermove":
						case "pointerout":
						case "pointerover":
						case "pointerup":
							c = ir;
							break;
						case "submit":
							c = ar;
							break;
						case "toggle":
						case "beforetoggle": c = lr;
					}
					var d = !!(t & 4), f = !d && (e === "scroll" || e === "scrollend"), p = d ? s === null ? null : s + "Capture" : s;
					d = [];
					for (var m = r, h; m !== null;) {
						var g = m;
						if (h = g.stateNode, g = g.tag, g !== 5 && g !== 26 && g !== 27 || h === null || p === null || (g = En(m, p), g != null && d.push(qf(m, g, h))), f) break;
						m = m.return;
					}
					0 < d.length && (s = new c(s, u, null, n, i), o.push({
						event: s,
						listeners: d
					}));
				}
			}
			if (!(t & 7)) {
				a: {
					if (c = e === "mouseover" || e === "pointerover", s = e === "mouseout" || e === "pointerout", c && n !== yn && (u = n.relatedTarget || n.fromElement) && (F(u) || u[Ot])) break a;
					(s || c) && (u = i.window === i ? i : (c = i.ownerDocument) ? c.defaultView || c.parentWindow : window, s ? (c = n.relatedTarget || n.toElement, s = r, c = c ? F(c) : null, c !== null && (f = l(c), d = c.tag, c !== f || d !== 5 && d !== 27 && d !== 6) && (c = null)) : (s = null, c = r), s !== c && (d = Kn, g = "onMouseLeave", p = "onMouseEnter", m = "mouse", (e === "pointerout" || e === "pointerover") && (d = ir, g = "onPointerLeave", p = "onPointerEnter", m = "pointer"), f = s == null ? u : It(s), h = c == null ? u : It(c), u = new d(g, m + "leave", s, n, i), u.target = f, u.relatedTarget = h, g = null, F(i) === r && (d = new d(p, m + "enter", c, n, i), d.target = h, d.relatedTarget = f, g = d), f = g, d = s && c ? ne(s, c, Yf) : null, s !== null && Xf(o, u, s, d, !1), c !== null && f !== null && Xf(o, f, c, d, !0)));
				}
				a: {
					if (s = r ? It(r) : window, c = s.nodeName && s.nodeName.toLowerCase(), c === "select" || c === "input" && s.type === "file") var _ = kr;
					else if (Cr(s)) {
						if (Ar) _ = zr;
						else {
							_ = Lr;
							var v = Ir;
						}
					} else c = s.nodeName, !c || c.toLowerCase() !== "input" || s.type !== "checkbox" && s.type !== "radio" ? r && mn(r.elementType) && (_ = kr) : _ = Rr;
					if (_ &&= _(e, r)) {
						wr(o, _, n, i);
						break a;
					}
					v && v(e, s, r);
				}
				switch (v = r ? It(r) : window, e) {
					case "focusin":
						(Cr(v) || v.contentEditable === "true") && (Xr = v, Zr = r, Qr = null);
						break;
					case "focusout":
						Qr = Zr = Xr = null;
						break;
					case "mousedown":
						$r = !0;
						break;
					case "contextmenu":
					case "mouseup":
					case "dragend":
						$r = !1, ei(o, n, i);
						break;
					case "selectionchange": if (Yr) break;
					case "keydown":
					case "keyup": ei(o, n, i);
				}
				var y;
				if (dr) b: {
					switch (e) {
						case "compositionstart":
							var b = "onCompositionStart";
							break b;
						case "compositionend":
							b = "onCompositionEnd";
							break b;
						case "compositionupdate":
							b = "onCompositionUpdate";
							break b;
					}
					b = void 0;
				}
				else yr ? _r(e, n) && (b = "onCompositionEnd") : e === "keydown" && n.keyCode === 229 && (b = "onCompositionStart");
				b && (mr && n.locale !== "ko" && (yr || b !== "onCompositionStart" ? b === "onCompositionEnd" && yr && (y = Nn()) : (An = i, jn = "value" in An ? An.value : An.textContent, yr = !0)), v = Jf(r, b), 0 < v.length && (b = new Zn(b, e, null, n, i), o.push({
					event: b,
					listeners: v
				}), y ? b.data = y : (y = vr(n), y !== null && (b.data = y)))), (y = pr ? br(e, n) : xr(e, n)) && (b = Jf(r, "onBeforeInput"), 0 < b.length && (v = new Zn("onBeforeInput", "beforeinput", null, n, i), o.push({
					event: v,
					listeners: b
				}), v.data = y)), If(o, e, r, n, i);
			}
			Vf(o, t);
		});
	}
	function qf(e, t, n) {
		return {
			instance: e,
			listener: t,
			currentTarget: n
		};
	}
	function Jf(e, t) {
		for (var n = t + "Capture", r = []; e !== null;) {
			var i = e, a = i.stateNode;
			if (i = i.tag, i !== 5 && i !== 26 && i !== 27 || a === null || (i = En(e, n), i != null && r.unshift(qf(e, i, a)), i = En(e, t), i != null && r.push(qf(e, i, a))), e.tag === 3) return r;
			e = e.return;
		}
		return [];
	}
	function Yf(e) {
		if (e === null) return null;
		do
			e = e.return;
		while (e && e.tag !== 5 && e.tag !== 27);
		return e || null;
	}
	function Xf(e, t, n, r, i) {
		for (var a = t._reactName, o = []; n !== null && n !== r;) {
			var s = n, c = s.alternate, l = s.stateNode;
			if (s = s.tag, c !== null && c === r) break;
			s !== 5 && s !== 26 && s !== 27 || l === null || (c = l, i ? (l = En(n, a), l != null && o.unshift(qf(n, l, c))) : i || (l = En(n, a), l != null && o.push(qf(n, l, c)))), n = n.return;
		}
		o.length !== 0 && e.push({
			event: t,
			listeners: o
		});
	}
	var Zf = /\r\n?/g, Qf = /\u0000|\uFFFD/g;
	function $f(e) {
		return (typeof e == "string" ? e : "" + e).replace(Zf, "\n").replace(Qf, "");
	}
	function ep(e, t) {
		return t = $f(t), $f(e) === t;
	}
	function $(e, t, n, r, i, a) {
		switch (n) {
			case "children":
				if (typeof r == "string") t === "body" || t === "textarea" && r === "" || un(e, r);
				else if (typeof r == "number" || typeof r == "bigint") t !== "body" && un(e, "" + r);
				else return;
				break;
			case "className":
				Jt(e, "class", r);
				break;
			case "tabIndex":
				Jt(e, "tabindex", r);
				break;
			case "dir":
			case "role":
			case "viewBox":
			case "width":
			case "height":
				Jt(e, n, r);
				break;
			case "style":
				pn(e, r, a);
				return;
			case "data": if (t !== "object") {
				Jt(e, "data", r);
				break;
			}
			case "src":
			case "href":
				if (r === "" && (t !== "a" || n !== "href") || r == null || typeof r == "function" || typeof r == "symbol" || typeof r == "boolean") {
					e.removeAttribute(n);
					break;
				}
				r = _n(r), e.setAttribute(n, r);
				break;
			case "action":
			case "formAction":
				if (typeof r == "function") {
					e.setAttribute(n, "javascript:throw new Error('A React form was unexpectedly submitted. If you called form.submit() manually, consider using form.requestSubmit() instead. If you\\'re trying to use event.stopPropagation() in a submit event handler, consider also calling event.preventDefault().')");
					break;
				}
				if (typeof a == "function" && (n === "formAction" ? (t !== "input" && $(e, t, "name", i.name, i, null), $(e, t, "formEncType", i.formEncType, i, null), $(e, t, "formMethod", i.formMethod, i, null), $(e, t, "formTarget", i.formTarget, i, null)) : ($(e, t, "encType", i.encType, i, null), $(e, t, "method", i.method, i, null), $(e, t, "target", i.target, i, null))), r == null || typeof r == "symbol" || typeof r == "boolean") {
					e.removeAttribute(n);
					break;
				}
				r = _n(r), e.setAttribute(n, r);
				break;
			case "onClick":
				r != null && (e.onclick = vn);
				return;
			case "onScroll":
				r != null && Q("scroll", e);
				return;
			case "onScrollEnd":
				r != null && Q("scrollend", e);
				return;
			case "dangerouslySetInnerHTML":
				if (r != null) {
					if (typeof r != "object" || !("__html" in r)) throw Error(s(61));
					if (n = r.__html, n != null) {
						if (i.children != null) throw Error(s(60));
						a?.__html !== n && (e.innerHTML = n);
					}
				}
				break;
			case "multiple":
				e.multiple = r && typeof r != "function" && typeof r != "symbol";
				break;
			case "muted":
				e.muted = r && typeof r != "function" && typeof r != "symbol";
				break;
			case "suppressContentEditableWarning":
			case "suppressHydrationWarning":
			case "defaultValue":
			case "defaultChecked":
			case "innerHTML":
			case "ref": break;
			case "autoFocus": break;
			case "xlinkHref":
				if (r == null || typeof r == "function" || typeof r == "boolean" || typeof r == "symbol") {
					e.removeAttribute("xlink:href");
					break;
				}
				n = _n(r), e.setAttributeNS("http://www.w3.org/1999/xlink", "xlink:href", n);
				break;
			case "contentEditable":
			case "spellCheck":
			case "draggable":
			case "value":
			case "autoReverse":
			case "externalResourcesRequired":
			case "focusable":
			case "preserveAlpha":
				r != null && typeof r != "function" && typeof r != "symbol" ? e.setAttribute(n, r) : e.removeAttribute(n);
				break;
			case "inert":
			case "allowFullScreen":
			case "async":
			case "autoPlay":
			case "controls":
			case "credentialless":
			case "default":
			case "defer":
			case "disabled":
			case "disablePictureInPicture":
			case "disableRemotePlayback":
			case "formNoValidate":
			case "hidden":
			case "loop":
			case "noModule":
			case "noValidate":
			case "open":
			case "playsInline":
			case "readOnly":
			case "required":
			case "reversed":
			case "scoped":
			case "seamless":
			case "itemScope":
				r && typeof r != "function" && typeof r != "symbol" ? e.setAttribute(n, "") : e.removeAttribute(n);
				break;
			case "capture":
			case "download":
				!0 === r ? e.setAttribute(n, "") : !1 !== r && r != null && typeof r != "function" && typeof r != "symbol" ? e.setAttribute(n, r) : e.removeAttribute(n);
				break;
			case "cols":
			case "rows":
			case "size":
			case "span":
				r != null && typeof r != "function" && typeof r != "symbol" && !isNaN(r) && 1 <= r ? e.setAttribute(n, r) : e.removeAttribute(n);
				break;
			case "rowSpan":
			case "start":
				r == null || typeof r == "function" || typeof r == "symbol" || isNaN(r) ? e.removeAttribute(n) : e.setAttribute(n, r);
				break;
			case "popover":
				Q("beforetoggle", e), Q("toggle", e), qt(e, "popover", r);
				break;
			case "xlinkActuate":
				Yt(e, "http://www.w3.org/1999/xlink", "xlink:actuate", r);
				break;
			case "xlinkArcrole":
				Yt(e, "http://www.w3.org/1999/xlink", "xlink:arcrole", r);
				break;
			case "xlinkRole":
				Yt(e, "http://www.w3.org/1999/xlink", "xlink:role", r);
				break;
			case "xlinkShow":
				Yt(e, "http://www.w3.org/1999/xlink", "xlink:show", r);
				break;
			case "xlinkTitle":
				Yt(e, "http://www.w3.org/1999/xlink", "xlink:title", r);
				break;
			case "xlinkType":
				Yt(e, "http://www.w3.org/1999/xlink", "xlink:type", r);
				break;
			case "xmlBase":
				Yt(e, "http://www.w3.org/XML/1998/namespace", "xml:base", r);
				break;
			case "xmlLang":
				Yt(e, "http://www.w3.org/XML/1998/namespace", "xml:lang", r);
				break;
			case "xmlSpace":
				Yt(e, "http://www.w3.org/XML/1998/namespace", "xml:space", r);
				break;
			case "is":
				qt(e, "is", r);
				break;
			case "innerText":
			case "textContent": return;
			default: if (!(2 < n.length) || n[0] !== "o" && n[0] !== "O" || n[1] !== "n" && n[1] !== "N") n = hn.get(n) || n, qt(e, n, r);
			else return;
		}
		z = !0;
	}
	function tp(e, t, n, r, i, a) {
		switch (n) {
			case "style":
				pn(e, r, a);
				return;
			case "dangerouslySetInnerHTML":
				if (r != null) {
					if (typeof r != "object" || !("__html" in r)) throw Error(s(61));
					if (n = r.__html, n != null) {
						if (i.children != null) throw Error(s(60));
						a?.__html !== n && (e.innerHTML = n);
					}
				}
				break;
			case "children":
				if (typeof r == "string") un(e, r);
				else if (typeof r == "number" || typeof r == "bigint") un(e, "" + r);
				else return;
				break;
			case "onScroll":
				r != null && Q("scroll", e);
				return;
			case "onScrollEnd":
				r != null && Q("scrollend", e);
				return;
			case "onClick":
				r != null && (e.onclick = vn);
				return;
			case "suppressContentEditableWarning":
			case "suppressHydrationWarning":
			case "innerHTML":
			case "ref": return;
			case "innerText":
			case "textContent": return;
			default:
				if (!zt.hasOwnProperty(n)) a: {
					if (n[0] === "o" && n[1] === "n" && (i = n.endsWith("Capture"), a = n.slice(2, i ? n.length - 7 : void 0), t = e[Dt] || null, t = t == null ? null : t[n], typeof t == "function" && e.removeEventListener(a, t, i), typeof r == "function")) {
						typeof t != "function" && t !== null && (n in e ? e[n] = null : e.hasAttribute(n) && e.removeAttribute(n)), e.addEventListener(a, r, i);
						break a;
					}
					z = !0, n in e ? e[n] = r : !0 === r ? e.setAttribute(n, "") : qt(e, n, r);
				}
				return;
		}
		z = !0;
	}
	function np(e, t, n) {
		switch (t) {
			case "div":
			case "span":
			case "svg":
			case "path":
			case "a":
			case "g":
			case "p":
			case "li": break;
			case "img":
				Q("error", e), Q("load", e);
				var r = !1, i = !1, a;
				for (a in n) if (n.hasOwnProperty(a)) {
					var o = n[a];
					if (o != null) switch (a) {
						case "src":
							r = !0;
							break;
						case "srcSet":
							i = !0;
							break;
						case "children":
						case "dangerouslySetInnerHTML": throw Error(s(137, t));
						default: $(e, t, a, o, n, null);
					}
				}
				i && $(e, t, "srcSet", n.srcSet, n, null), r && $(e, t, "src", n.src, n, null);
				return;
			case "input":
				Q("invalid", e);
				var c = a = o = i = null, l = null, u = null;
				for (r in n) if (n.hasOwnProperty(r)) {
					var d = n[r];
					if (d != null) switch (r) {
						case "name":
							i = d;
							break;
						case "type":
							o = d;
							break;
						case "checked":
							l = d;
							break;
						case "defaultChecked":
							u = d;
							break;
						case "value":
							a = d;
							break;
						case "defaultValue":
							c = d;
							break;
						case "children":
						case "dangerouslySetInnerHTML":
							if (d != null) throw Error(s(137, t));
							break;
						default: $(e, t, r, d, n, null);
					}
				}
				an(e, a, c, l, u, o, i, !1);
				return;
			case "select":
				for (i in Q("invalid", e), r = o = a = null, n) if (n.hasOwnProperty(i) && (c = n[i], c != null)) switch (i) {
					case "value":
						a = c;
						break;
					case "defaultValue":
						o = c;
						break;
					case "multiple": r = c;
					default: $(e, t, i, c, n, null);
				}
				t = a, n = o, e.multiple = !!r, t == null ? n != null && sn(e, !!r, n, !0) : sn(e, !!r, t, !1);
				return;
			case "textarea":
				for (o in Q("invalid", e), a = i = r = null, n) if (n.hasOwnProperty(o) && (c = n[o], c != null)) switch (o) {
					case "value":
						r = c;
						break;
					case "defaultValue":
						i = c;
						break;
					case "children":
						a = c;
						break;
					case "dangerouslySetInnerHTML":
						if (c != null) throw Error(s(91));
						break;
					default: $(e, t, o, c, n, null);
				}
				ln(e, r, i, a);
				return;
			case "option":
				for (l in n) if (n.hasOwnProperty(l) && (r = n[l], r != null)) switch (l) {
					case "selected":
						e.selected = r && typeof r != "function" && typeof r != "symbol";
						break;
					default: $(e, t, l, r, n, null);
				}
				return;
			case "dialog":
				Q("beforetoggle", e), Q("toggle", e), Q("cancel", e), Q("close", e);
				break;
			case "iframe":
			case "object":
				Q("load", e);
				break;
			case "video":
			case "audio":
				for (r = 0; r < zf.length; r++) Q(zf[r], e);
				break;
			case "image":
				Q("error", e), Q("load", e);
				break;
			case "details":
				Q("toggle", e);
				break;
			case "embed":
			case "source":
			case "link": Q("error", e), Q("load", e);
			case "area":
			case "base":
			case "br":
			case "col":
			case "hr":
			case "keygen":
			case "meta":
			case "param":
			case "track":
			case "wbr":
			case "menuitem":
				for (u in n) if (n.hasOwnProperty(u) && (r = n[u], r != null)) switch (u) {
					case "children":
					case "dangerouslySetInnerHTML": throw Error(s(137, t));
					default: $(e, t, u, r, n, null);
				}
				return;
			default: if (mn(t)) {
				for (d in n) n.hasOwnProperty(d) && (r = n[d], r !== void 0 && tp(e, t, d, r, n, void 0));
				return;
			}
		}
		for (c in n) n.hasOwnProperty(c) && (r = n[c], r != null && $(e, t, c, r, n, null));
	}
	var rp = {};
	function ip(e, t, n, r) {
		switch (t) {
			case "div":
			case "span":
			case "svg":
			case "path":
			case "a":
			case "g":
			case "p":
			case "li": break;
			case "input":
				var i = null, a = null, o = null, c = null, l = null, u = null, d = null;
				for (m in n) {
					var f = n[m];
					if (n.hasOwnProperty(m) && f != null) switch (m) {
						case "checked": break;
						case "value": break;
						case "defaultValue": l = f;
						default: r.hasOwnProperty(m) || $(e, t, m, null, r, f);
					}
				}
				for (var p in r) {
					var m = r[p];
					if (f = n[p], r.hasOwnProperty(p) && (m != null || f != null)) switch (p) {
						case "type":
							m !== f && (z = !0), a = m;
							break;
						case "name":
							m !== f && (z = !0), i = m;
							break;
						case "checked":
							m !== f && (z = !0), u = m;
							break;
						case "defaultChecked":
							m !== f && (z = !0), d = m;
							break;
						case "value":
							m !== f && (z = !0), o = m;
							break;
						case "defaultValue":
							m !== f && (z = !0), c = m;
							break;
						case "children":
						case "dangerouslySetInnerHTML":
							if (m != null) throw Error(s(137, t));
							break;
						default: m !== f && $(e, t, p, m, r, f);
					}
				}
				rn(e, o, c, l, u, d, a, i);
				return;
			case "select":
				for (a in m = o = c = p = null, n) if (l = n[a], n.hasOwnProperty(a) && l != null) switch (a) {
					case "value": break;
					case "multiple": m = l;
					default: r.hasOwnProperty(a) || $(e, t, a, null, r, l);
				}
				for (i in r) if (a = r[i], l = n[i], r.hasOwnProperty(i) && (a != null || l != null)) switch (i) {
					case "value":
						a !== l && (z = !0), p = a;
						break;
					case "defaultValue":
						a !== l && (z = !0), c = a;
						break;
					case "multiple": a !== l && (z = !0), o = a;
					default: a !== l && $(e, t, i, a, r, l);
				}
				t = c, n = o, r = m, p == null ? !!r != !!n && (t == null ? sn(e, !!n, n ? [] : "", !1) : sn(e, !!n, t, !0)) : sn(e, !!n, p, !1);
				return;
			case "textarea":
				for (c in m = p = null, n) if (i = n[c], n.hasOwnProperty(c) && i != null && !r.hasOwnProperty(c)) switch (c) {
					case "value": break;
					case "children": break;
					default: $(e, t, c, null, r, i);
				}
				for (o in r) if (i = r[o], a = n[o], r.hasOwnProperty(o) && (i != null || a != null)) switch (o) {
					case "value":
						i !== a && (z = !0), p = i;
						break;
					case "defaultValue":
						i !== a && (z = !0), m = i;
						break;
					case "children": break;
					case "dangerouslySetInnerHTML":
						if (i != null) throw Error(s(91));
						break;
					default: i !== a && $(e, t, o, i, r, a);
				}
				cn(e, p, m);
				return;
			case "option":
				for (var h in n) if (p = n[h], n.hasOwnProperty(h) && p != null && !r.hasOwnProperty(h)) switch (h) {
					case "selected":
						e.selected = !1;
						break;
					default: $(e, t, h, null, r, p);
				}
				for (l in r) if (p = r[l], m = n[l], r.hasOwnProperty(l) && p !== m && (p != null || m != null)) switch (l) {
					case "selected":
						p !== m && (z = !0), e.selected = p && typeof p != "function" && typeof p != "symbol";
						break;
					default: $(e, t, l, p, r, m);
				}
				return;
			case "img":
			case "link":
			case "area":
			case "base":
			case "br":
			case "col":
			case "embed":
			case "hr":
			case "keygen":
			case "meta":
			case "param":
			case "source":
			case "track":
			case "wbr":
			case "menuitem":
				for (var g in n) p = n[g], n.hasOwnProperty(g) && p != null && !r.hasOwnProperty(g) && $(e, t, g, null, r, p);
				for (u in r) if (p = r[u], m = n[u], r.hasOwnProperty(u) && p !== m && (p != null || m != null)) switch (u) {
					case "children":
					case "dangerouslySetInnerHTML":
						if (p != null) throw Error(s(137, t));
						break;
					default: $(e, t, u, p, r, m);
				}
				return;
			default: if (mn(t)) {
				for (var _ in n) p = n[_], n.hasOwnProperty(_) && p !== void 0 && !r.hasOwnProperty(_) && tp(e, t, _, void 0, r, p);
				for (d in r) p = r[d], m = n[d], !r.hasOwnProperty(d) || p === m || p === void 0 && m === void 0 || tp(e, t, d, p, r, m);
				return;
			}
		}
		for (var v in n) p = n[v], n.hasOwnProperty(v) && p != null && !r.hasOwnProperty(v) && $(e, t, v, null, r, p);
		for (f in r) p = r[f], m = n[f], !r.hasOwnProperty(f) || p === m || p == null && m == null || $(e, t, f, p, r, m);
	}
	function ap(e) {
		switch (e) {
			case "css":
			case "script":
			case "font":
			case "img":
			case "image":
			case "input":
			case "link": return !0;
			default: return !1;
		}
	}
	function op() {
		if (typeof performance.getEntriesByType == "function") {
			for (var e = 0, t = 0, n = performance.getEntriesByType("resource"), r = 0; r < n.length; r++) {
				var i = n[r], a = i.transferSize, o = i.initiatorType, s = i.duration;
				if (a && s && ap(o)) {
					for (o = 0, s = i.responseEnd, r += 1; r < n.length; r++) {
						var c = n[r], l = c.startTime;
						if (l > s) break;
						var u = c.transferSize, d = c.initiatorType;
						u && ap(d) && (c = c.responseEnd, o += u * (c < s ? 1 : (s - l) / (c - l)));
					}
					if (--r, t += 8 * (a + o) / (i.duration / 1e3), e++, 10 < e) break;
				}
			}
			if (0 < e) return t / e / 1e6;
		}
		return navigator.connection && (e = navigator.connection.downlink, typeof e == "number") ? e : 5;
	}
	var sp = null, cp = null;
	function lp(e) {
		return e.nodeType === 9 ? e : e.ownerDocument;
	}
	function up(e) {
		switch (e) {
			case "http://www.w3.org/2000/svg": return 1;
			case "http://www.w3.org/1998/Math/MathML": return 2;
			default: return 0;
		}
	}
	function dp(e, t) {
		if (e === 0) switch (t) {
			case "svg": return 1;
			case "math": return 2;
			default: return 0;
		}
		return e === 1 && t === "foreignObject" ? 0 : e;
	}
	function fp(e, t, n, r) {
		return n = lp(n).createElement(e), n[Et] = r, n[Dt] = t, np(n, e, t), L(n), n;
	}
	function pp(e, t) {
		return e === "textarea" || e === "noscript" || typeof t.children == "string" || typeof t.children == "number" || typeof t.children == "bigint" || typeof t.dangerouslySetInnerHTML == "object" && t.dangerouslySetInnerHTML !== null && t.dangerouslySetInnerHTML.__html != null;
	}
	var mp = null;
	function hp() {
		var e = window.event;
		return e && e.type === "popstate" ? e !== mp && (mp = e, !0) : (mp = null, !1);
	}
	var gp = typeof setTimeout == "function" ? setTimeout : void 0, _p = typeof clearTimeout == "function" ? clearTimeout : void 0, vp = typeof Promise == "function" ? Promise : void 0, yp = typeof requestAnimationFrame == "function" ? requestAnimationFrame : gp, bp = typeof queueMicrotask == "function" ? queueMicrotask : vp === void 0 ? gp : function(e) {
		return vp.resolve(null).then(e).catch(xp);
	};
	function xp(e) {
		setTimeout(function() {
			throw e;
		});
	}
	function Sp(e) {
		return e === "head";
	}
	function Cp(e, t) {
		var n = t, r = 0;
		do {
			var i = n.nextSibling;
			if (e.removeChild(n), i && i.nodeType === 8) {
				if (n = i.data, n === "/$" || n === "/&") {
					if (r === 0) {
						e.removeChild(i), Hh(t);
						return;
					}
					r--;
				} else if (n === "$" || n === "$?" || n === "$~" || n === "$!" || n === "&") r++;
				else if (n === "html") _m(e.ownerDocument.documentElement);
				else if (n === "head") {
					n = e.ownerDocument.head, _m(n);
					for (var a = n.firstChild; a;) {
						var o = a.nextSibling, s = a.nodeName;
						a[Nt] || s === "SCRIPT" || s === "STYLE" || s === "LINK" && a.rel.toLowerCase() === "stylesheet" || n.removeChild(a), a = o;
					}
				} else n === "body" && _m(e.ownerDocument.body);
			}
			n = i;
		} while (n);
		Hh(t);
	}
	function wp(e, t) {
		var n = e;
		e = 0;
		do {
			var r = n.nextSibling;
			if (n.nodeType === 1 ? t ? (n._stashedDisplay = n.style.display, n.style.display = "none") : (n.style.display = n._stashedDisplay || "", n.getAttribute("style") === "" && n.removeAttribute("style")) : n.nodeType === 3 && (t ? (n._stashedText = n.nodeValue, n.nodeValue = "") : n.nodeValue = n._stashedText || ""), r && r.nodeType === 8) {
				if (n = r.data, n === "/$") {
					if (e === 0) break;
					e--;
				} else n !== "$" && n !== "$?" && n !== "$~" && n !== "$!" || e++;
			}
			n = r;
		} while (n);
	}
	function Tp(e, t, n) {
		if (t = CSS.escape(t) === t ? t : "r-" + btoa(t).replace(/=/g, ""), e.style.viewTransitionName = t, n != null && (e.style.viewTransitionClass = n), n = getComputedStyle(e), n.display === "inline") {
			if (t = e.getClientRects(), t.length === 1) var r = 1;
			else for (var i = r = 0; i < t.length; i++) {
				var a = t[i];
				0 < a.width && 0 < a.height && r++;
			}
			r === 1 && (e = e.style, e.display = t.length === 1 ? "inline-block" : "block", e.marginTop = "-" + n.paddingTop, e.marginBottom = "-" + n.paddingBottom);
		}
	}
	function Ep(e, t) {
		e = e.style, t = t.style;
		var n = t == null ? null : t.hasOwnProperty("viewTransitionName") ? t.viewTransitionName : t.hasOwnProperty("view-transition-name") ? t["view-transition-name"] : null;
		e.viewTransitionName = n == null || typeof n == "boolean" ? "" : ("" + n).trim(), n = t == null ? null : t.hasOwnProperty("viewTransitionClass") ? t.viewTransitionClass : t.hasOwnProperty("view-transition-class") ? t["view-transition-class"] : null, e.viewTransitionClass = n == null || typeof n == "boolean" ? "" : ("" + n).trim(), e.display === "inline-block" && (t == null ? e.display = e.margin = "" : (n = t.display, e.display = n == null || typeof n == "boolean" ? "" : n, n = t.margin, n == null ? (n = t.hasOwnProperty("marginTop") ? t.marginTop : t["margin-top"], e.marginTop = n == null || typeof n == "boolean" ? "" : n, t = t.hasOwnProperty("marginBottom") ? t.marginBottom : t["margin-bottom"], e.marginBottom = t == null || typeof t == "boolean" ? "" : t) : e.margin = n));
	}
	function Dp(e, t, n) {
		return n = n.ownerDocument.defaultView, {
			rect: e,
			abs: t.position === "absolute" || t.position === "fixed",
			clip: t.clipPath !== "none" || t.overflow !== "visible" || t.filter !== "none" || t.mask !== "none" || t.mask !== "none" || t.borderRadius !== "0px",
			view: 0 <= e.bottom && 0 <= e.right && e.top <= n.innerHeight && e.left <= n.innerWidth
		};
	}
	function Op(e) {
		return Dp(e.getBoundingClientRect(), getComputedStyle(e), e);
	}
	function kp(e) {
		var t = e.getBoundingClientRect();
		t = new DOMRect(t.x + 2e4, t.y + 2e4, t.width, t.height);
		var n = getComputedStyle(e);
		return Dp(t, n, e);
	}
	function Ap(e) {
		return e.documentElement.clientHeight;
	}
	function jp(e) {
		this.addEventListener("load", e), this.addEventListener("error", e);
	}
	function Mp(e, t, n, r, i, a, o, s, c) {
		var l = t.nodeType === 9 ? t : t.ownerDocument;
		try {
			var u = l.startViewTransition({
				update: function() {
					var t = l.defaultView, n = t.navigation && t.navigation.transition, o = l.fonts.status;
					r();
					var s = [];
					if (o === "loaded" && (Ap(l), l.fonts.status === "loading" && s.push(l.fonts.ready)), o = s.length, e !== null) for (var c = e.suspenseyImages, u = 0, d = 0; d < c.length; d++) {
						var f = c[d];
						if (!f.complete) {
							var p = f.getBoundingClientRect();
							if (0 < p.bottom && 0 < p.right && p.top < t.innerHeight && p.left < t.innerWidth) {
								if (u += Xm(f), u > $m) {
									s.length = o;
									break;
								}
								f = new Promise(jp.bind(f)), s.push(f);
							}
						}
					}
					if (0 < s.length) return t = Promise.race([Promise.all(s), new Promise(function(e) {
						return setTimeout(e, 500);
					})]).then(i, i), (n ? Promise.allSettled([n.finished, t]) : t).then(a, a);
					if (i(), n) return n.finished.then(a, a);
					a();
				},
				types: n
			});
			l.__reactViewTransition = u;
			var d = [];
			return u.ready.then(function() {
				for (var e = l.documentElement.getAnimations({ subtree: !0 }), t = 0; t < e.length; t++) {
					var n = e[t], r = n.effect, i = r.pseudoElement;
					if (i != null && i.startsWith("::view-transition")) {
						d.push(n), n = r.getKeyframes();
						for (var a = i = void 0, s = !0, c = 0; c < n.length; c++) {
							var u = n[c], f = u.width;
							if (i === void 0) i = f;
							else if (i !== f) {
								s = !1;
								break;
							}
							if (f = u.height, a === void 0) a = f;
							else if (a !== f) {
								s = !1;
								break;
							}
							delete u.width, delete u.height, u.transform === "none" && delete u.transform;
						}
						s && i !== void 0 && a !== void 0 && (r.setKeyframes(n), s = getComputedStyle(r.target, r.pseudoElement), s.width !== i || s.height !== a) && (s = n[0], s.width = i, s.height = a, s = n[n.length - 1], s.width = i, s.height = a, r.setKeyframes(n));
					}
				}
				o();
			}, function(e) {
				l.__reactViewTransition === u && (l.__reactViewTransition = null);
				try {
					if (typeof e == "object" && e) switch (e.name) {
						case "InvalidStateError": (e.message === "View transition was skipped because document visibility state is hidden." || e.message === "Skipping view transition because document visibility state has become hidden." || e.message === "Skipping view transition because viewport size changed." || e.message === "Transition was aborted because of invalid state") && (e = null);
					}
					e !== null && c(e);
				} finally {
					r(), i(), o();
				}
			}), u.finished.finally(function() {
				for (var e = 0; e < d.length; e++) d[e].cancel();
				l.__reactViewTransition === u && (l.__reactViewTransition = null), s();
			}), u;
		} catch {
			return r(), i(), o(), null;
		}
	}
	function Np(e, t) {
		this._scope = document.documentElement, this._selector = "::view-transition-" + e + "(" + t + ")";
	}
	Np.prototype.animate = function(e, t) {
		return t = typeof t == "number" ? { duration: t } : w({}, t), t.pseudoElement = this._selector, this._scope.animate(e, t);
	}, Np.prototype.getAnimations = function() {
		for (var e = this._scope, t = this._selector, n = e.getAnimations({ subtree: !0 }), r = [], i = 0; i < n.length; i++) {
			var a = n[i].effect;
			a !== null && a.target === e && a.pseudoElement === t && r.push(n[i]);
		}
		return r;
	}, Np.prototype.getComputedStyle = function() {
		return getComputedStyle(this._scope, this._selector);
	};
	function Pp(e) {
		return {
			name: e,
			group: new Np("group", e),
			imagePair: new Np("image-pair", e),
			old: new Np("old", e),
			new: new Np("new", e)
		};
	}
	function Fp(e) {
		this._fragmentFiber = e, this._observers = this._eventListeners = null;
	}
	Fp.prototype.addEventListener = function(e, t, n) {
		var r = null, i = null;
		if (!(n != null && typeof n != "boolean" && (r = n.signal || null, r !== null && r.aborted))) {
			this._eventListeners === null && (this._eventListeners = []);
			var a = this._eventListeners;
			if (Bp(a, e, t, n) === -1) {
				var o = this, s = t;
				n != null && typeof n != "boolean" && !0 === n.once && (s = function(r) {
					o.removeEventListener(e, t, n), typeof t == "function" ? t.call(this, r) : t.handleEvent(r);
				}), r !== null && (i = o.removeEventListener.bind(o, e, t, n), r.addEventListener("abort", i, { once: !0 }), i = r.removeEventListener.bind(r, "abort", i)), r = Rp(n), a.push({
					type: e,
					listener: t,
					optionsOrUseCapture: n,
					attachedListener: s,
					cleanup: i
				}), h(this._fragmentFiber.child, !1, Ip, e, s, r);
			}
			this._eventListeners = a;
		}
	};
	function Ip(e, t, n, r) {
		return b(e).addEventListener(t, n, r), !1;
	}
	Fp.prototype.removeEventListener = function(e, t, n) {
		var r = this._eventListeners;
		if (r !== null && (t = Bp(r, e, t, n), t !== -1)) {
			var i = r[t];
			n = i.attachedListener;
			var a = i.cleanup;
			i = Rp(i.optionsOrUseCapture), h(this._fragmentFiber.child, !1, Lp, e, n, i), r.splice(t, 1), a !== null && a();
		}
	};
	function Lp(e, t, n, r) {
		return b(e).removeEventListener(t, n, r), !1;
	}
	function Rp(e) {
		return e != null && typeof e != "boolean" && (!0 === e.once || e.signal instanceof AbortSignal) ? {
			capture: e.capture,
			passive: e.passive
		} : e;
	}
	function zp(e) {
		return e == null ? "c=0" : typeof e == "boolean" ? "c=" + (e ? "1" : "0") : "c=" + (e.capture ? "1" : "0");
	}
	function Bp(e, t, n, r) {
		if (e.length === 0) return -1;
		r = zp(r);
		for (var i = 0; i < e.length; i++) {
			var a = e[i];
			if (a.type === t && a.listener === n && zp(a.optionsOrUseCapture) === r) return i;
		}
		return -1;
	}
	Fp.prototype.dispatchEvent = function(e) {
		var t = g(this._fragmentFiber);
		if (t === null) return !0;
		t = b(t);
		var n = this._eventListeners;
		if (n !== null && 0 < n.length || !e.bubbles) {
			var r = t.nodeType === 9 ? t.createComment("") : document.createTextNode("");
			if (n) for (var i = 0; i < n.length; i++) {
				var a = n[i];
				r.addEventListener(a.type, a.attachedListener, Rp(a.optionsOrUseCapture));
			}
			if (t.appendChild(r), e = r.dispatchEvent(e), n) for (i = 0; i < n.length; i++) a = n[i], r.removeEventListener(a.type, a.attachedListener, Rp(a.optionsOrUseCapture));
			return t.removeChild(r), e;
		}
		return t.dispatchEvent(e);
	}, Fp.prototype.focus = function(e) {
		h(this._fragmentFiber.child, !0, Vp, e, void 0, void 0);
	};
	function Vp(e, t) {
		return e.tag !== 6 && (e = b(e), pm(e, t));
	}
	Fp.prototype.focusLast = function(e) {
		var t = [];
		h(this._fragmentFiber.child, !0, Hp, t, void 0, void 0);
		for (var n = t.length - 1; 0 <= n && !Vp(t[n], e); n--);
	};
	function Hp(e, t) {
		return t.push(e), !1;
	}
	Fp.prototype.blur = function() {
		var e = g(this._fragmentFiber);
		e !== null && (e = b(e), e = lp(e).activeElement, e !== null && h(this._fragmentFiber.child, !1, Up, e, void 0, void 0));
	};
	function Up(e, t) {
		return e.tag !== 6 && (e = b(e), e === t || e.contains(t) ? (t.blur(), !0) : !1);
	}
	Fp.prototype.observeUsing = function(e) {
		this._observers === null && (this._observers = /* @__PURE__ */ new Set()), this._observers.add(e), h(this._fragmentFiber.child, !1, Wp, e, void 0, void 0);
	};
	function Wp(e, t) {
		return e.tag === 6 || (e = b(e), t.observe(e)), !1;
	}
	Fp.prototype.unobserveUsing = function(e) {
		var t = this._observers;
		if (t !== null && t.has(e)) {
			t.delete(e), h(this._fragmentFiber.child, !1, Gp, e, void 0, void 0);
			for (var n = t = 0; n < Kp.length; n++) {
				var r = Kp[n];
				r.fragmentInstance === this && r.observer === e ? e.unobserve(r.instance) : Kp[t++] = r;
			}
			Kp.length = t;
		}
	};
	function Gp(e, t) {
		return e.tag === 6 || (e = b(e), t.unobserve(e)), !1;
	}
	var Kp = [], qp = !1;
	function Jp(e, t, n) {
		Kp.push({
			fragmentInstance: e,
			observer: t,
			instance: n
		}), qp || (qp = !0, mm(function() {
			qp = !1;
			var e = Kp;
			Kp = [];
			for (var t = 0; t < e.length; t++) {
				var n = e[t];
				n.observer.unobserve(n.instance);
			}
		}));
	}
	Fp.prototype.getClientRects = function() {
		var e = [];
		return h(this._fragmentFiber.child, !1, Yp, e, void 0, void 0), e;
	};
	function Yp(e, t) {
		if (e.tag === 6) {
			e = e.stateNode;
			var n = e.ownerDocument.createRange();
			n.selectNodeContents(e), t.push.apply(t, n.getClientRects());
		} else e = b(e), t.push.apply(t, e.getClientRects());
		return !1;
	}
	Fp.prototype.getRootNode = function(e) {
		var t = g(this._fragmentFiber);
		return t === null ? this : b(t).getRootNode(e);
	}, Fp.prototype.compareDocumentPosition = function(e) {
		var t = g(this._fragmentFiber);
		if (t === null) return Node.DOCUMENT_POSITION_DISCONNECTED;
		var n = [];
		h(this._fragmentFiber.child, !1, Hp, n, void 0, void 0);
		var r = b(t);
		if (n.length === 0) {
			if (n = r, _(this._fragmentFiber)) {
				a: {
					for (t = this._fragmentFiber.return; t !== null;) {
						if (t.tag === 4) {
							t = t.stateNode.containerInfo;
							break a;
						}
						if (t.tag === 3 || t.tag === 5 || t.tag === 27) break;
						t = t.return;
					}
					t = null;
				}
				t != null && (n = t);
			}
			t = this._fragmentFiber;
			var i = r = n.compareDocumentPosition(e);
			return n === e ? i = Node.DOCUMENT_POSITION_CONTAINS : r & Node.DOCUMENT_POSITION_CONTAINED_BY && (n = v(t)[1], n === null ? i = Node.DOCUMENT_POSITION_PRECEDING : (e = b(n).compareDocumentPosition(e), i = e === 0 || e & Node.DOCUMENT_POSITION_FOLLOWING ? Node.DOCUMENT_POSITION_FOLLOWING : Node.DOCUMENT_POSITION_PRECEDING)), i |= Node.DOCUMENT_POSITION_IMPLEMENTATION_SPECIFIC;
		}
		t = b(n[0]), i = b(n[n.length - 1]);
		var a = _(this._fragmentFiber) ? t.parentElement : r;
		if (a == null) return Node.DOCUMENT_POSITION_DISCONNECTED;
		r = a.compareDocumentPosition(t) & Node.DOCUMENT_POSITION_CONTAINED_BY, a = a.compareDocumentPosition(i) & Node.DOCUMENT_POSITION_CONTAINED_BY;
		var o = t.compareDocumentPosition(e), s = i.compareDocumentPosition(e), c = o & Node.DOCUMENT_POSITION_CONTAINED_BY || s & Node.DOCUMENT_POSITION_CONTAINED_BY;
		return s = r && a && o & Node.DOCUMENT_POSITION_FOLLOWING && s & Node.DOCUMENT_POSITION_PRECEDING, t = r && t === e || a && i === e || c || s ? Node.DOCUMENT_POSITION_CONTAINED_BY : !r && t === e || !a && i === e ? Node.DOCUMENT_POSITION_IMPLEMENTATION_SPECIFIC : o, t & Node.DOCUMENT_POSITION_DISCONNECTED || t & Node.DOCUMENT_POSITION_IMPLEMENTATION_SPECIFIC || Xp(t, this._fragmentFiber, n[0], n[n.length - 1], e) ? t : Node.DOCUMENT_POSITION_IMPLEMENTATION_SPECIFIC;
	};
	function Xp(e, t, n, r, i) {
		var a = F(i);
		if (e & Node.DOCUMENT_POSITION_CONTAINED_BY) {
			if (n = !!a) a: {
				for (; a !== null;) {
					if (a.tag === 7 && (a === t || a.alternate === t)) {
						n = !0;
						break a;
					}
					a = a.return;
				}
				n = !1;
			}
			return n;
		}
		if (e & Node.DOCUMENT_POSITION_CONTAINS) {
			if (a === null) return a = i.ownerDocument, i === a || i === a.documentElement || i === a.body;
			a: {
				for (a = t, t = g(t); a !== null;) {
					if (!(a.tag !== 5 && a.tag !== 3 && a.tag !== 27 || a !== t && a.alternate !== t)) {
						a = !0;
						break a;
					}
					a = a.return;
				}
				a = !1;
			}
			return a;
		}
		return e & Node.DOCUMENT_POSITION_PRECEDING ? ((t = !!a) && !(t = a === n) && (t = ne(n, a, C), t === null ? t = !1 : (h(t, !0, S, a, n), a = ee, ee = null, t = a !== null)), t) : e & Node.DOCUMENT_POSITION_FOLLOWING ? ((t = !!a) && !(t = a === r) && (t = ne(r, a, C), t === null ? t = !1 : (h(t, !0, te, a, r), a = ee, x = ee = null, t = a !== null)), t) : !1;
	}
	function Zp(e, t) {
		var n = e.ownerDocument.createRange();
		n.selectNodeContents(e), e = n.getBoundingClientRect(), window.scrollTo(window.scrollX + e.left, t ? window.scrollY + e.top : window.scrollY + e.bottom - window.innerHeight);
	}
	Fp.prototype.scrollIntoView = function(e) {
		if (typeof e == "object") throw Error(s(566));
		var t = [];
		h(this._fragmentFiber.child, !1, Hp, t, void 0, void 0);
		var n = !1 !== e;
		if (t.length === 0) {
			var r = v(this._fragmentFiber);
			if (r = n ? r[1] || r[0] || g(this._fragmentFiber) : r[0] || r[1], r === null) return;
			if (r.tag === 6) {
				e = b(r), Zp(e, n);
				return;
			}
			if (r = b(r), r.nodeType !== 9) {
				if (r.nodeType === 11) {
					n = "host" in r ? r.host : null, n !== null && n.scrollIntoView(e);
					return;
				}
				r.scrollIntoView(e);
			}
		}
		for (r = n ? t.length - 1 : 0; r !== (n ? -1 : t.length);) {
			var i = t[r];
			i.tag === 6 ? (i = b(i), Zp(i, n)) : b(i).scrollIntoView(e), r += n ? -1 : 1;
		}
	};
	function Qp(e, t) {
		return e = b(e), $p(e, t), !1;
	}
	function $p(e, t) {
		e.reactFragments ??= /* @__PURE__ */ new Set(), e.reactFragments.add(t);
	}
	function em(e, t) {
		var n = t._eventListeners;
		if (n !== null) for (var r = 0; r < n.length; r++) {
			var i = n[r];
			e.addEventListener(i.type, i.attachedListener, Rp(i.optionsOrUseCapture));
		}
		e.nodeType !== 3 && (n = t._observers, n !== null && n.forEach(function(n) {
			for (var r = 0, i = 0; i < Kp.length; i++) {
				var a = Kp[i];
				(a.fragmentInstance !== t || a.observer !== n || a.instance !== e) && (Kp[r++] = a);
			}
			Kp.length = r, n.observe(e);
		}), $p(e, t));
	}
	function tm(e, t) {
		var n = t._eventListeners;
		if (n !== null) for (var r = 0; r < n.length; r++) {
			var i = n[r];
			e.removeEventListener(i.type, i.attachedListener, Rp(i.optionsOrUseCapture));
		}
		e.nodeType !== 3 && (n = t._observers, n !== null && n.forEach(function(n) {
			typeof n.rootMargin == "string" ? Jp(t, n, e) : n.unobserve(e);
		}), e.reactFragments != null && e.reactFragments.delete(t));
	}
	function nm(e) {
		var t = e.firstChild;
		for (t && t.nodeType === 10 && (t = t.nextSibling); t;) {
			var n = t;
			switch (t = t.nextSibling, n.nodeName) {
				case "HTML":
				case "HEAD":
				case "BODY":
					nm(n), Ft(n);
					continue;
				case "SCRIPT":
				case "STYLE": continue;
				case "LINK": if (n.rel.toLowerCase() === "stylesheet") continue;
			}
			e.removeChild(n);
		}
	}
	function rm(e, t, n, r) {
		for (; e.nodeType === 1;) {
			var i = n;
			if (e.nodeName.toLowerCase() !== t.toLowerCase()) {
				if (!r && (e.nodeName !== "INPUT" || e.type !== "hidden")) break;
			} else if (!r) {
				if (t === "input" && e.type === "hidden") {
					var a = i.name == null ? null : "" + i.name;
					if (i.type === "hidden" && e.getAttribute("name") === a) return e;
				} else return e;
			} else if (!e[Nt]) switch (t) {
				case "meta":
					if (!e.hasAttribute("itemprop")) break;
					return e;
				case "link":
					if (a = e.getAttribute("rel"), a === "stylesheet" && e.hasAttribute("data-precedence") || a !== i.rel || e.getAttribute("href") !== (i.href == null || i.href === "" ? null : i.href) || e.getAttribute("crossorigin") !== (i.crossOrigin == null ? null : i.crossOrigin) || e.getAttribute("title") !== (i.title == null ? null : i.title)) break;
					return e;
				case "style":
					if (e.hasAttribute("data-precedence")) break;
					return e;
				case "script":
					if (a = e.getAttribute("src"), (a !== (i.src == null ? null : i.src) || e.getAttribute("type") !== (i.type == null ? null : i.type) || e.getAttribute("crossorigin") !== (i.crossOrigin == null ? null : i.crossOrigin)) && a && e.hasAttribute("async") && !e.hasAttribute("itemprop")) break;
					return e;
				default: return e;
			}
			if (e = lm(e.nextSibling), e === null) break;
		}
		return null;
	}
	function im(e, t, n) {
		if (t === "") return null;
		for (; e.nodeType !== 3;) if ((e.nodeType !== 1 || e.nodeName !== "INPUT" || e.type !== "hidden") && !n || (e = lm(e.nextSibling), e === null)) return null;
		return e;
	}
	function am(e, t) {
		for (; e.nodeType !== 8;) if ((e.nodeType !== 1 || e.nodeName !== "INPUT" || e.type !== "hidden") && !t || (e = lm(e.nextSibling), e === null)) return null;
		return e;
	}
	function om(e) {
		return e.data === "$?" || e.data === "$~";
	}
	function sm(e) {
		return e.data === "$!" || e.data === "$?" && e.ownerDocument.readyState !== "loading";
	}
	function cm(e, t) {
		var n = e.ownerDocument;
		if (e.data === "$~") e._reactRetry = t;
		else if (e.data !== "$?" || n.readyState !== "loading") t();
		else {
			var r = function() {
				t(), n.removeEventListener("DOMContentLoaded", r);
			};
			n.addEventListener("DOMContentLoaded", r), e._reactRetry = r;
		}
	}
	function lm(e) {
		for (; e != null; e = e.nextSibling) {
			var t = e.nodeType;
			if (t === 1 || t === 3) break;
			if (t === 8) {
				if (t = e.data, t === "$" || t === "$!" || t === "$?" || t === "$~" || t === "&" || t === "F!" || t === "F") break;
				if (t === "/$" || t === "/&") return null;
			}
		}
		return e;
	}
	var um = null;
	function dm(e) {
		e = e.nextSibling;
		for (var t = 0; e;) {
			if (e.nodeType === 8) {
				var n = e.data;
				if (n === "/$" || n === "/&") {
					if (t === 0) return lm(e.nextSibling);
					t--;
				} else n !== "$" && n !== "$!" && n !== "$?" && n !== "$~" && n !== "&" || t++;
			}
			e = e.nextSibling;
		}
		return null;
	}
	function fm(e) {
		e = e.previousSibling;
		for (var t = 0; e;) {
			if (e.nodeType === 8) {
				var n = e.data;
				if (n === "$" || n === "$!" || n === "$?" || n === "$~" || n === "&") {
					if (t === 0) return e;
					t--;
				} else n !== "/$" && n !== "/&" || t++;
			}
			e = e.previousSibling;
		}
		return null;
	}
	function pm(e, t) {
		function n() {
			r = !0;
		}
		if (e.ownerDocument.activeElement === e) return !0;
		var r = !1;
		try {
			e.ownerDocument.addEventListener("focus", n, !0), (e.focus || HTMLElement.prototype.focus).call(e, t);
		} finally {
			e.ownerDocument.removeEventListener("focus", n, !0);
		}
		return r;
	}
	function mm(e) {
		yp(function() {
			yp(function(t) {
				return e(t);
			});
		});
	}
	function hm(e, t, n) {
		switch (t = lp(n), e) {
			case "html":
				if (e = t.documentElement, !e) throw Error(s(452));
				return e;
			case "head":
				if (e = t.head, !e) throw Error(s(453));
				return e;
			case "body":
				if (e = t.body, !e) throw Error(s(454));
				return e;
			default: throw Error(s(451));
		}
	}
	function gm(e, t, n) {
		for (var r in n) {
			var i = n[r];
			n.hasOwnProperty(r) && i != null && $(e, t, r, null, rp, i);
		}
		n.dangerouslySetInnerHTML != null && (e.textContent = ""), e.onclick === vn && (e.onclick = null), Ft(e);
	}
	function _m(e) {
		for (var t = e.attributes; t.length;) e.removeAttributeNode(t[0]);
		Ft(e);
	}
	var vm = /* @__PURE__ */ new Map(), ym = /* @__PURE__ */ new Set();
	function bm(e) {
		if (typeof e.getRootNode == "function") {
			var t = e.getRootNode();
			if (t.nodeType === 9 || t.nodeType === 11) return t;
		}
		return e.nodeType === 9 ? e : e.ownerDocument;
	}
	var xm = A.d;
	A.d = {
		f: Sm,
		r: Cm,
		D: Em,
		C: Dm,
		L: Om,
		m: km,
		X: jm,
		S: Am,
		M: Mm
	};
	function Sm() {
		var e = xm.f(), t = zd();
		return e || t;
	}
	function Cm(e) {
		var t = I(e);
		t !== null && t.tag === 5 && t.type === "form" ? nc(t) : xm.r(e);
	}
	var wm = typeof document > "u" ? null : document;
	function Tm(e, t, n) {
		var r = wm;
		if (r && typeof t == "string" && t) {
			var i = nn(t);
			i = "link[rel=\"" + e + "\"][href=\"" + i + "\"]", typeof n == "string" && (i += "[crossorigin=\"" + n + "\"]"), ym.has(i) || (ym.add(i), e = {
				rel: e,
				crossOrigin: n,
				href: t
			}, r.querySelector(i) === null && (t = r.createElement("link"), np(t, "link", e), L(t), r.head.appendChild(t)));
		}
	}
	function Em(e) {
		xm.D(e), Tm("dns-prefetch", e, null);
	}
	function Dm(e, t) {
		xm.C(e, t), Tm("preconnect", e, t);
	}
	function Om(e, t, n) {
		xm.L(e, t, n);
		var r = wm;
		if (r && e && t) {
			var i = "link[rel=\"preload\"][as=\"" + nn(t) + "\"]";
			t === "image" && n && n.imageSrcSet ? (i += "[imagesrcset=\"" + nn(n.imageSrcSet) + "\"]", typeof n.imageSizes == "string" && (i += "[imagesizes=\"" + nn(n.imageSizes) + "\"]")) : i += "[href=\"" + nn(e) + "\"]";
			var a = i;
			switch (t) {
				case "style":
					a = Pm(e);
					break;
				case "script": a = Rm(e);
			}
			if (!(vm.has(a) || (e = w({
				rel: "preload",
				href: t === "image" && n && n.imageSrcSet ? void 0 : e,
				as: t
			}, n), vm.set(a, e), r.querySelector(i) !== null || t === "style" && r.querySelector(Fm(a)) || t === "script" && r.querySelector(zm(a))))) {
				var o = r.createElement("link");
				np(o, "link", e), t === "style" && (o[Pt] = !0, o.onload = o.onerror = function() {
					R(o);
				}), L(o), r.head.appendChild(o);
			}
		}
	}
	function km(e, t) {
		xm.m(e, t);
		var n = wm;
		if (n && e) {
			var r = t && typeof t.as == "string" ? t.as : "script", i = "link[rel=\"modulepreload\"][as=\"" + nn(r) + "\"][href=\"" + nn(e) + "\"]", a = i;
			switch (r) {
				case "audioworklet":
				case "paintworklet":
				case "serviceworker":
				case "sharedworker":
				case "worker":
				case "script": a = Rm(e);
			}
			if (!vm.has(a) && (e = w({
				rel: "modulepreload",
				href: e
			}, t), vm.set(a, e), n.querySelector(i) === null)) {
				switch (r) {
					case "audioworklet":
					case "paintworklet":
					case "serviceworker":
					case "sharedworker":
					case "worker":
					case "script": if (n.querySelector(zm(a))) return;
				}
				r = n.createElement("link"), np(r, "link", e), L(r), n.head.appendChild(r);
			}
		}
	}
	function Am(e, t, n) {
		xm.S(e, t, n);
		var r = wm;
		if (r && e) {
			var i = Lt(r).hoistableStyles, a = Pm(e);
			t ||= "default";
			var o = i.get(a);
			if (!o) {
				var s = {
					loading: 0,
					preload: null
				};
				if (o = r.querySelector(Fm(a))) s.loading = 5;
				else {
					e = w({
						rel: "stylesheet",
						href: e,
						"data-precedence": t
					}, n), (n = vm.get(a)) && Hm(e, n);
					var c = o = r.createElement("link");
					L(c), np(c, "link", e), c._p = new Promise(function(e, t) {
						c.onload = e, c.onerror = t;
					}), c.addEventListener("load", function() {
						s.loading |= 1;
					}), c.addEventListener("error", function() {
						s.loading |= 2;
					}), s.loading |= 4, Vm(o, t, r);
				}
				o = {
					type: "stylesheet",
					instance: o,
					count: 1,
					state: s
				}, i.set(a, o);
			}
		}
	}
	function jm(e, t) {
		xm.X(e, t);
		var n = wm;
		if (n && e) {
			var r = Lt(n).hoistableScripts, i = Rm(e), a = r.get(i);
			a || (a = n.querySelector(zm(i)), a || (e = w({
				src: e,
				async: !0
			}, t), (t = vm.get(i)) && Um(e, t), a = n.createElement("script"), L(a), np(a, "link", e), n.head.appendChild(a)), a = {
				type: "script",
				instance: a,
				count: 1,
				state: null
			}, r.set(i, a));
		}
	}
	function Mm(e, t) {
		xm.M(e, t);
		var n = wm;
		if (n && e) {
			var r = Lt(n).hoistableScripts, i = Rm(e), a = r.get(i);
			a || (a = n.querySelector(zm(i)), a || (e = w({
				src: e,
				async: !0,
				type: "module"
			}, t), (t = vm.get(i)) && Um(e, t), a = n.createElement("script"), L(a), np(a, "link", e), n.head.appendChild(a)), a = {
				type: "script",
				instance: a,
				count: 1,
				state: null
			}, r.set(i, a));
		}
	}
	function Nm(e, t, n, r) {
		var i = (i = De.current) ? bm(i) : null;
		if (!i) throw Error(s(446));
		switch (e) {
			case "meta":
			case "title": return null;
			case "style": return typeof n.precedence == "string" && typeof n.href == "string" ? (n = Pm(n.href), t = Lt(i).hoistableStyles, r = t.get(n), r || (r = {
				type: "style",
				instance: null,
				count: 0,
				state: null
			}, t.set(n, r)), r) : {
				type: "void",
				instance: null,
				count: 0,
				state: null
			};
			case "link":
				if (n.rel === "stylesheet" && typeof n.href == "string" && typeof n.precedence == "string") {
					e = Pm(n.href);
					var a = Lt(i).hoistableStyles, o = a.get(e);
					if (o || (i = i.ownerDocument || i, o = {
						type: "stylesheet",
						instance: null,
						count: 0,
						state: {
							loading: 0,
							preload: null
						}
					}, a.set(e, o), (a = i.querySelector(Fm(e))) ? a._p || (o.instance = a, o.state.loading = 5) : (a = vm.get(e), a || (a = {
						rel: "preload",
						as: "style",
						href: n.href,
						crossOrigin: n.crossOrigin,
						integrity: n.integrity,
						media: n.media,
						hrefLang: n.hrefLang,
						referrerPolicy: n.referrerPolicy
					}, vm.set(e, a)), Lm(i, e, a, o.state))), t && r === null) throw Error(s(528, ""));
					return o;
				}
				if (t && r !== null) throw Error(s(529, ""));
				return null;
			case "script": return t = n.async, n = n.src, typeof n == "string" && t && typeof t != "function" && typeof t != "symbol" ? (n = Rm(n), t = Lt(i).hoistableScripts, r = t.get(n), r || (r = {
				type: "script",
				instance: null,
				count: 0,
				state: null
			}, t.set(n, r)), r) : {
				type: "void",
				instance: null,
				count: 0,
				state: null
			};
			default: throw Error(s(444, e));
		}
	}
	function Pm(e) {
		return "href=\"" + nn(e) + "\"";
	}
	function Fm(e) {
		return "link[rel=\"stylesheet\"][" + e + "]";
	}
	function Im(e) {
		return w({}, e, {
			"data-precedence": e.precedence,
			precedence: null
		});
	}
	function Lm(e, t, n, r) {
		if (t = e.querySelector("link[rel=\"preload\"][as=\"style\"][" + t + "]")) {
			if (!0 !== t[Pt]) {
				r.loading = 1;
				return;
			}
		} else t = e.createElement("link"), t[Pt] = !0, t.onload = t.onerror = R.bind(null, t), np(t, "link", n), L(t), e.head.appendChild(t);
		r.preload = t, t.addEventListener("load", function() {
			return r.loading |= 1;
		}), t.addEventListener("error", function() {
			return r.loading |= 2;
		});
	}
	function Rm(e) {
		return "[src=\"" + nn(e) + "\"]";
	}
	function zm(e) {
		return "script[async]" + e;
	}
	function Bm(e, t, n) {
		if (t.count++, t.instance === null) switch (t.type) {
			case "style":
				var r = e.querySelector("style[data-href~=\"" + nn(n.href) + "\"]");
				if (r) return t.instance = r, L(r), r;
				var i = w({}, n, {
					"data-href": n.href,
					"data-precedence": n.precedence,
					href: null,
					precedence: null
				});
				return r = (e.ownerDocument || e).createElement("style"), L(r), np(r, "style", i), Vm(r, n.precedence, e), t.instance = r;
			case "stylesheet":
				i = Pm(n.href);
				var a = e.querySelector(Fm(i));
				if (a) return t.state.loading |= 4, t.instance = a, L(a), a;
				r = Im(n), (i = vm.get(i)) && Hm(r, i), a = (e.ownerDocument || e).createElement("link"), L(a);
				var o = a;
				return o._p = new Promise(function(e, t) {
					o.onload = e, o.onerror = t;
				}), np(a, "link", r), t.state.loading |= 4, Vm(a, n.precedence, e), t.instance = a;
			case "script": return a = Rm(n.src), (i = e.querySelector(zm(a))) ? (t.instance = i, L(i), i) : (r = n, (i = vm.get(a)) && (r = w({}, n), Um(r, i)), e = e.ownerDocument || e, i = e.createElement("script"), L(i), np(i, "link", r), e.head.appendChild(i), t.instance = i);
			case "void": return null;
			default: throw Error(s(443, t.type));
		}
		else t.type === "stylesheet" && !(t.state.loading & 4) && (r = t.instance, t.state.loading |= 4, Vm(r, n.precedence, e));
		return t.instance;
	}
	function Vm(e, t, n) {
		for (var r = n.querySelectorAll("link[rel=\"stylesheet\"][data-precedence],style[data-precedence]"), i = r.length ? r[r.length - 1] : null, a = i, o = 0; o < r.length; o++) {
			var s = r[o];
			if (s.dataset.precedence === t) a = s;
			else if (a !== i) break;
		}
		a ? a.parentNode.insertBefore(e, a.nextSibling) : (t = n.nodeType === 9 ? n.head : n, t.insertBefore(e, t.firstChild));
	}
	function Hm(e, t) {
		e.crossOrigin ??= t.crossOrigin, e.referrerPolicy ??= t.referrerPolicy, e.title ??= t.title;
	}
	function Um(e, t) {
		e.crossOrigin ??= t.crossOrigin, e.referrerPolicy ??= t.referrerPolicy, e.integrity ??= t.integrity;
	}
	var Wm = null;
	function Gm(e, t, n) {
		if (Wm === null) {
			var r = /* @__PURE__ */ new Map(), i = Wm = /* @__PURE__ */ new Map();
			i.set(n, r);
		} else i = Wm, r = i.get(n), r || (r = /* @__PURE__ */ new Map(), i.set(n, r));
		if (r.has(e)) return r;
		for (r.set(e, null), n = n.getElementsByTagName(e), i = 0; i < n.length; i++) {
			var a = n[i];
			if (!(a[Nt] || a[Et] || e === "link" && a.getAttribute("rel") === "stylesheet") && a.namespaceURI !== "http://www.w3.org/2000/svg") {
				var o = a.getAttribute(t) || "";
				o = e + o;
				var s = r.get(o);
				s ? s.push(a) : r.set(o, [a]);
			}
		}
		return r;
	}
	function Km(e, t, n) {
		e = e.ownerDocument || e, e.head.insertBefore(n, t === "title" ? e.querySelector("head > title") : null);
	}
	function qm(e, t, n) {
		if (n === 1 || t.itemProp != null) return !1;
		switch (e) {
			case "meta":
			case "title": return !0;
			case "style":
				if (typeof t.precedence != "string" || typeof t.href != "string" || t.href === "") break;
				return !0;
			case "link":
				if (typeof t.rel != "string" || typeof t.href != "string" || t.href === "" || t.onLoad || t.onError) break;
				switch (t.rel) {
					case "stylesheet": return e = t.disabled, typeof t.precedence == "string" && e == null;
					default: return !0;
				}
			case "script": if (t.async && typeof t.async != "function" && typeof t.async != "symbol" && !t.onLoad && !t.onError && t.src && typeof t.src == "string") return !0;
		}
		return !1;
	}
	function Jm(e, t) {
		return e === "img" && t.src != null && t.src !== "" && t.onLoad == null && t.loading !== "lazy";
	}
	function Ym(e) {
		return !(e.type === "stylesheet" && !(e.state.loading & 3));
	}
	function Xm(e) {
		return (e.width || 100) * (e.height || 100) * (typeof devicePixelRatio == "number" ? devicePixelRatio : 1) * .25;
	}
	function Zm(e, t) {
		typeof t.decode == "function" && (e.imgCount++, t.complete || (e.imgBytes += Xm(t), e.suspenseyImages.push(t)), e = rh.bind(e), t.decode().then(e, e));
	}
	function Qm(e, t, n, r) {
		if (n.type === "stylesheet" && (typeof r.media != "string" || !1 !== matchMedia(r.media).matches) && !(n.state.loading & 4)) {
			if (n.instance === null) {
				var i = Pm(r.href), a = t.querySelector(Fm(i));
				if (a) {
					t = a._p, typeof t == "object" && t && typeof t.then == "function" && (e.count++, e = nh.bind(e), t.then(e, e)), n.state.loading |= 4, n.instance = a, L(a);
					return;
				}
				a = t.ownerDocument || t, r = Im(r), (i = vm.get(i)) && Hm(r, i), a = a.createElement("link"), L(a);
				var o = a;
				o._p = new Promise(function(e, t) {
					o.onload = e, o.onerror = t;
				}), np(a, "link", r), n.instance = a;
			}
			e.stylesheets === null && (e.stylesheets = /* @__PURE__ */ new Map()), e.stylesheets.set(n, t), (t = n.state.preload) && !(n.state.loading & 3) && (e.count++, n = nh.bind(e), t.addEventListener("load", n), t.addEventListener("error", n));
		}
	}
	var $m = 0;
	function eh(e, t) {
		return e.stylesheets && e.count === 0 && ah(e, e.stylesheets), 0 < e.count || 0 < e.imgCount ? function(n) {
			var r = setTimeout(function() {
				if (e.stylesheets && ah(e, e.stylesheets), e.unsuspend) {
					var t = e.unsuspend;
					e.unsuspend = null, t();
				}
			}, 6e4 + t);
			0 < e.imgBytes && $m === 0 && ($m = 62500 * op());
			var i = setTimeout(function() {
				if (e.waitingForImages = !1, e.count === 0 && (e.stylesheets && ah(e, e.stylesheets), e.unsuspend)) {
					var t = e.unsuspend;
					e.unsuspend = null, t();
				}
			}, (e.imgBytes > $m ? 50 : 800) + t);
			return e.unsuspend = n, function() {
				e.unsuspend = null, clearTimeout(r), clearTimeout(i);
			};
		} : null;
	}
	function th(e) {
		if (e.count === 0 && (e.imgCount === 0 || !e.waitingForImages)) {
			if (e.stylesheets) ah(e, e.stylesheets);
			else if (e.unsuspend) {
				var t = e.unsuspend;
				e.unsuspend = null, t();
			}
		}
	}
	function nh() {
		this.count--, th(this);
	}
	function rh() {
		this.imgCount--, th(this);
	}
	var ih = null;
	function ah(e, t) {
		e.stylesheets = null, e.unsuspend !== null && (e.count++, ih = /* @__PURE__ */ new Map(), t.forEach(oh, e), ih = null, nh.call(e));
	}
	function oh(e, t) {
		if (!(t.state.loading & 4)) {
			var n = ih.get(e);
			if (n) var r = n.get(null);
			else {
				n = /* @__PURE__ */ new Map(), ih.set(e, n);
				for (var i = e.querySelectorAll("link[data-precedence],style[data-precedence]"), a = 0; a < i.length; a++) {
					var o = i[a];
					(o.nodeName === "LINK" || o.getAttribute("media") !== "not all") && (n.set(o.dataset.precedence, o), r = o);
				}
				r && n.set(null, r);
			}
			i = t.instance, o = i.getAttribute("data-precedence"), a = n.get(o) || r, a === r && n.set(null, i), n.set(o, i), this.count++, r = nh.bind(this), i.addEventListener("load", r), i.addEventListener("error", r), a ? a.parentNode.insertBefore(i, a.nextSibling) : (e = e.nodeType === 9 ? e.head : e, e.insertBefore(i, e.firstChild)), t.state.loading |= 4;
		}
	}
	var sh = {
		$$typeof: se,
		Provider: null,
		Consumer: null,
		_currentValue: Se,
		_currentValue2: Se,
		_threadCount: 0
	};
	function ch(e, t, n, r, i, a, o, s, c) {
		this.tag = 1, this.containerInfo = e, this.pingCache = this.current = this.pendingChildren = null, this.timeoutHandle = -1, this.callbackNode = this.next = this.pendingContext = this.context = this.cancelPendingCommit = null, this.callbackPriority = 0, this.expirationTimes = ht(-1), this.entangledLanes = this.shellSuspendCounter = this.errorRecoveryDisabledLanes = this.expiredLanes = this.warmLanes = this.pingedLanes = this.suspendedLanes = this.pendingLanes = 0, this.entanglements = ht(0), this.hiddenUpdates = ht(null), this.identifierPrefix = r, this.onUncaughtError = i, this.onCaughtError = a, this.onRecoverableError = o, this.pooledCache = null, this.pooledCacheLanes = 0, this.formState = c, this.transitionTypes = null, this.incompleteTransitions = /* @__PURE__ */ new Map();
	}
	function lh(e, t, n, r, i, a, o, s, c, l, u, d) {
		return e = new ch(e, t, n, o, c, l, u, d, s), t = 1, !0 === a && (t |= 24), a = Mi(3, null, null, t), e.current = a, a.stateNode = e, t = ja(), t.refCount++, e.pooledCache = t, t.refCount++, a.memoizedState = {
			element: r,
			isDehydrated: n,
			cache: t
		}, mo(a), e;
	}
	function uh(e) {
		return e ? (e = Ai, e) : Ai;
	}
	function dh(e, t, n, r, i, a) {
		i = uh(i), r.context === null ? r.context = i : r.pendingContext = i, r = go(t), r.payload = { element: n }, a = a === void 0 ? null : a, a !== null && (r.callback = a), n = _o(e, r, t), n !== null && (Pd(n, e, t), vo(n, e, t));
	}
	function fh(e, t) {
		if (e = e.memoizedState, e !== null && e.dehydrated !== null) {
			var n = e.retryLane;
			e.retryLane = n !== 0 && n < t ? n : t;
		}
	}
	function ph(e, t) {
		fh(e, t), (e = e.alternate) && fh(e, t);
	}
	function mh(e) {
		if (e.tag === 13 || e.tag === 31) {
			var t = Di(e, 67108864);
			t !== null && Pd(t, e, 67108864), ph(e, 67108864);
		}
	}
	function hh(e) {
		if (e.tag === 13 || e.tag === 31) {
			var t = jd();
			t = xt(t);
			var n = Di(e, t);
			n !== null && Pd(n, e, t), ph(e, t);
		}
	}
	var gh = !0;
	function _h(e, t, n, r) {
		var i = k.T;
		k.T = null;
		var a = A.p;
		try {
			A.p = 2, yh(e, t, n, r);
		} finally {
			A.p = a, k.T = i;
		}
	}
	function vh(e, t, n, r) {
		var i = k.T;
		k.T = null;
		var a = A.p;
		try {
			A.p = 8, yh(e, t, n, r);
		} finally {
			A.p = a, k.T = i;
		}
	}
	function yh(e, t, n, r) {
		if (gh) {
			var i = bh(r);
			if (i === null) Kf(e, t, r, xh, n), Mh(e, r);
			else if (Ph(i, e, t, n, r)) r.stopPropagation();
			else if (Mh(e, r), t & 4 && -1 < jh.indexOf(e)) {
				for (; i !== null;) {
					var a = I(i);
					if (a !== null) switch (a.tag) {
						case 3:
							if (a = a.stateNode, a.current.memoizedState.isDehydrated) {
								var o = lt(a.pendingLanes);
								if (o !== 0) {
									var s = a;
									for (s.pendingLanes |= 2, s.entangledLanes |= 2; o;) {
										var c = 1 << 31 - nt(o);
										s.entanglements[1] |= c, o &= ~c;
									}
									Ef(a), !(K & 6) && (gd = P() + 500, Df(0, !1));
								}
							}
							break;
						case 31:
						case 13: s = Di(a, 2), s !== null && Pd(s, a, 2), zd(), ph(a, 2);
					}
					if (a = bh(r), a === null && Kf(e, t, r, xh, n), a === i) break;
					i = a;
				}
				i !== null && r.stopPropagation();
			} else Kf(e, t, r, null, n);
		}
	}
	function bh(e) {
		return e = bn(e), Sh(e);
	}
	var xh = null;
	function Sh(e) {
		if (xh = null, e = F(e), e !== null) {
			var t = l(e);
			if (t === null) e = null;
			else {
				var n = t.tag;
				if (n === 13) {
					if (e = u(t), e !== null) return e;
					e = null;
				} else if (n === 31) {
					if (e = d(t), e !== null) return e;
					e = null;
				} else if (n === 3) {
					if (t.stateNode.current.memoizedState.isDehydrated) return t.tag === 3 ? t.stateNode.containerInfo : null;
					e = null;
				} else t !== e && (e = null);
			}
		}
		return xh = e, null;
	}
	function Ch(e) {
		switch (e) {
			case "beforetoggle":
			case "cancel":
			case "click":
			case "close":
			case "contextmenu":
			case "copy":
			case "cut":
			case "auxclick":
			case "dblclick":
			case "dragend":
			case "dragstart":
			case "drop":
			case "focusin":
			case "focusout":
			case "input":
			case "invalid":
			case "keydown":
			case "keypress":
			case "keyup":
			case "mousedown":
			case "mouseup":
			case "paste":
			case "pause":
			case "play":
			case "pointercancel":
			case "pointerdown":
			case "pointerup":
			case "ratechange":
			case "reset":
			case "seeked":
			case "submit":
			case "toggle":
			case "touchcancel":
			case "touchend":
			case "touchstart":
			case "volumechange":
			case "change":
			case "selectionchange":
			case "textInput":
			case "compositionstart":
			case "compositionend":
			case "compositionupdate":
			case "beforeblur":
			case "afterblur":
			case "beforeinput":
			case "blur":
			case "fullscreenchange":
			case "fullscreenerror":
			case "focus":
			case "hashchange":
			case "popstate":
			case "select":
			case "selectstart": return 2;
			case "drag":
			case "dragenter":
			case "dragexit":
			case "dragleave":
			case "dragover":
			case "mousemove":
			case "mouseout":
			case "mouseover":
			case "pointermove":
			case "pointerout":
			case "pointerover":
			case "resize":
			case "scroll":
			case "touchmove":
			case "wheel":
			case "mouseenter":
			case "mouseleave":
			case "pointerenter":
			case "pointerleave": return 8;
			case "message": switch (Ge()) {
				case Ke: return 2;
				case qe: return 8;
				case Je:
				case Ye: return 32;
				case Xe: return 268435456;
				default: return 32;
			}
			default: return 32;
		}
	}
	var wh = !1, Th = null, Eh = null, Dh = null, Oh = /* @__PURE__ */ new Map(), kh = /* @__PURE__ */ new Map(), Ah = [], jh = "mousedown mouseup touchcancel touchend touchstart auxclick dblclick pointercancel pointerdown pointerup dragend dragstart drop compositionend compositionstart keydown keypress keyup input textInput copy cut paste click change contextmenu reset".split(" ");
	function Mh(e, t) {
		switch (e) {
			case "focusin":
			case "focusout":
				Th = null;
				break;
			case "dragenter":
			case "dragleave":
				Eh = null;
				break;
			case "mouseover":
			case "mouseout":
				Dh = null;
				break;
			case "pointerover":
			case "pointerout":
				Oh.delete(t.pointerId);
				break;
			case "gotpointercapture":
			case "lostpointercapture": kh.delete(t.pointerId);
		}
	}
	function Nh(e, t, n, r, i, a) {
		return e === null || e.nativeEvent !== a ? (e = {
			blockedOn: t,
			domEventName: n,
			eventSystemFlags: r,
			nativeEvent: a,
			targetContainers: [i]
		}, t !== null && (t = I(t), t !== null && mh(t)), e) : (e.eventSystemFlags |= r, t = e.targetContainers, i !== null && t.indexOf(i) === -1 && t.push(i), e);
	}
	function Ph(e, t, n, r, i) {
		switch (t) {
			case "focusin": return Th = Nh(Th, e, t, n, r, i), !0;
			case "dragenter": return Eh = Nh(Eh, e, t, n, r, i), !0;
			case "mouseover": return Dh = Nh(Dh, e, t, n, r, i), !0;
			case "pointerover":
				var a = i.pointerId;
				return Oh.set(a, Nh(Oh.get(a) || null, e, t, n, r, i)), !0;
			case "gotpointercapture": return a = i.pointerId, kh.set(a, Nh(kh.get(a) || null, e, t, n, r, i)), !0;
		}
		return !1;
	}
	function Fh(e) {
		var t = F(e.target);
		if (t !== null) {
			var n = l(t);
			if (n !== null) {
				if (t = n.tag, t === 13) {
					if (t = u(n), t !== null) {
						e.blockedOn = t, wt(e.priority, function() {
							hh(n);
						});
						return;
					}
				} else if (t === 31) {
					if (t = d(n), t !== null) {
						e.blockedOn = t, wt(e.priority, function() {
							hh(n);
						});
						return;
					}
				} else if (t === 3 && n.stateNode.current.memoizedState.isDehydrated) {
					e.blockedOn = n.tag === 3 ? n.stateNode.containerInfo : null;
					return;
				}
			}
		}
		e.blockedOn = null;
	}
	function Ih(e) {
		if (e.blockedOn !== null) return !1;
		for (var t = e.targetContainers; 0 < t.length;) {
			var n = bh(e.nativeEvent);
			if (n === null) {
				n = e.nativeEvent;
				var r = new n.constructor(n.type, n);
				yn = r, n.target.dispatchEvent(r), yn = null;
			} else return t = I(n), t !== null && mh(t), e.blockedOn = n, !1;
			t.shift();
		}
		return !0;
	}
	function Lh(e, t, n) {
		Ih(e) && n.delete(t);
	}
	function Rh() {
		wh = !1, Th !== null && Ih(Th) && (Th = null), Eh !== null && Ih(Eh) && (Eh = null), Dh !== null && Ih(Dh) && (Dh = null), Oh.forEach(Lh), kh.forEach(Lh);
	}
	function zh(e, n) {
		e.blockedOn === n && (e.blockedOn = null, wh || (wh = !0, t.unstable_scheduleCallback(t.unstable_NormalPriority, Rh)));
	}
	var Bh = null;
	function Vh(e) {
		Bh !== e && (Bh = e, t.unstable_scheduleCallback(t.unstable_NormalPriority, function() {
			Bh === e && (Bh = null);
			for (var t = 0; t < e.length; t += 3) {
				var n = e[t], r = e[t + 1], i = e[t + 2];
				if (typeof r != "function") {
					if (Sh(r || n) === null) continue;
					break;
				}
				var a = I(n);
				a !== null && (e.splice(t, 3), t -= 3, ec(a, {
					pending: !0,
					data: i,
					method: n.method,
					action: r
				}, r, i));
			}
		}));
	}
	function Hh(e) {
		function t(t) {
			return zh(t, e);
		}
		Th !== null && zh(Th, e), Eh !== null && zh(Eh, e), Dh !== null && zh(Dh, e), Oh.forEach(t), kh.forEach(t);
		for (var n = 0; n < Ah.length; n++) {
			var r = Ah[n];
			r.blockedOn === e && (r.blockedOn = null);
		}
		for (; 0 < Ah.length && (n = Ah[0], n.blockedOn === null);) Fh(n), n.blockedOn === null && Ah.shift();
		if (n = (e.ownerDocument || e).$$reactFormReplay, n != null) for (r = 0; r < n.length; r += 3) {
			var i = n[r], a = n[r + 1], o = i[Dt] || null;
			if (typeof a == "function") o || Vh(n);
			else if (o) {
				var s = null;
				if (a && a.hasAttribute("formAction")) {
					if (i = a, o = a[Dt] || null) s = o.formAction;
					else if (Sh(i) !== null) continue;
				} else s = o.action;
				typeof s == "function" ? n[r + 1] = s : (n.splice(r, 3), r -= 3), Vh(n);
			}
		}
	}
	function Uh() {
		function e(e) {
			e.canIntercept && e.info === "react-transition" && e.intercept({
				handler: function() {
					return new Promise(function(e) {
						return i = e;
					});
				},
				focusReset: "manual",
				scroll: "manual"
			});
		}
		function t() {
			i !== null && (i(), i = null), r || setTimeout(n, 20);
		}
		function n() {
			if (!r && !navigation.transition) {
				var e = navigation.currentEntry;
				e && e.url != null && navigation.navigate(e.url, {
					state: e.getState(),
					info: "react-transition",
					history: "replace"
				});
			}
		}
		if (typeof navigation == "object") {
			var r = !1, i = null;
			return navigation.addEventListener("navigate", e), navigation.addEventListener("navigatesuccess", t), navigation.addEventListener("navigateerror", t), setTimeout(n, 100), function() {
				r = !0, navigation.removeEventListener("navigate", e), navigation.removeEventListener("navigatesuccess", t), navigation.removeEventListener("navigateerror", t), i !== null && (i(), i = null);
			};
		}
	}
	function Wh(e) {
		this._internalRoot = e;
	}
	Gh.prototype.render = Wh.prototype.render = function(e) {
		var t = this._internalRoot;
		if (t === null) throw Error(s(409));
		var n = t.current;
		dh(n, jd(), e, t, null, null);
	}, Gh.prototype.unmount = Wh.prototype.unmount = function() {
		var e = this._internalRoot;
		if (e !== null) {
			this._internalRoot = null;
			var t = e.containerInfo;
			dh(e.current, 2, null, e, null, null), zd(), t[Ot] = null;
		}
	};
	function Gh(e) {
		this._internalRoot = e;
	}
	Gh.prototype.unstable_scheduleHydration = function(e) {
		if (e) {
			var t = Ct();
			e = {
				blockedOn: null,
				target: e,
				priority: t
			};
			for (var n = 0; n < Ah.length && t !== 0 && t < Ah[n].priority; n++);
			Ah.splice(n, 0, e), n === 0 && Fh(e);
		}
	};
	var Kh = r.version;
	if (Kh !== "19.3.1") throw Error(s(527, Kh, "19.3.1"));
	A.findDOMNode = function(e) {
		var t = e._reactInternals;
		if (t === void 0) throw typeof e.render == "function" ? Error(s(188)) : (e = Object.keys(e).join(","), Error(s(268, e)));
		return e = p(t), e = e === null ? null : m(e), e = e === null ? null : e.stateNode, e;
	};
	var qh = {
		bundleType: 0,
		version: "19.3.1",
		rendererPackageName: "react-dom",
		currentDispatcherRef: k,
		reconcilerVersion: "19.3.1"
	};
	if (typeof __REACT_DEVTOOLS_GLOBAL_HOOK__ < "u") {
		var Jh = __REACT_DEVTOOLS_GLOBAL_HOOK__;
		if (!Jh.isDisabled && Jh.supportsFiber) try {
			$e = Jh.inject(qh), et = Jh;
		} catch {}
	}
	e.createRoot = function(e, t) {
		if (!c(e)) throw Error(s(299));
		var n = !1, r = "", i = Cc, a = wc, o = Tc;
		return t != null && (!0 === t.unstable_strictMode && (n = !0), t.identifierPrefix !== void 0 && (r = t.identifierPrefix), t.onUncaughtError !== void 0 && (i = t.onUncaughtError), t.onCaughtError !== void 0 && (a = t.onCaughtError), t.onRecoverableError !== void 0 && (o = t.onRecoverableError)), t = lh(e, 1, !1, null, null, n, r, null, i, a, o, Uh), e[Ot] = t.current, Wf(e), new Wh(t);
	};
})), c = /* @__PURE__ */ e(((e, t) => {
	function n() {
		if (typeof __REACT_DEVTOOLS_GLOBAL_HOOK__ < "u" && typeof __REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE == "function") try {
			__REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE(n);
		} catch (e) {
			console.error(e);
		}
	}
	n(), t.exports = s();
})), l = i(), u = c();
function d(e, t) {
	return e.available && !e.reference_only && e.mode_tags.includes(t) && e.mode_notes?.[t]?.fit !== "partial";
}
var f = {
	scene: [
		{
			value: "main",
			label: "主图"
		},
		{
			value: "support",
			label: "配角"
		},
		{
			value: "accent",
			label: "小点缀"
		}
	],
	scatter: [{
		value: "main",
		label: "主图"
	}, {
		value: "accent",
		label: "小点缀"
	}],
	bordered: [{
		value: "main",
		label: "中间主图"
	}, {
		value: "border",
		label: "上下边饰"
	}]
};
function p(e, t, n) {
	let r = f[t];
	return r ? Object.fromEntries(e.map((e, i) => [e, r.some((t) => t.value === n?.[e]) ? n[e] : t === "scene" && i > 0 ? "support" : "main"])) : {};
}
function m(e) {
	if (e.layout_engine !== "seamless-unit-v3") return {};
	let t = {};
	return e.asset_refs.forEach((n, r) => {
		let i = e.pattern_roles?.[e.pattern_slots?.[r] || ""];
		i && (t[n] = i);
	}), p(e.asset_refs, e.template_mode, t);
}
var h = class extends Error {
	status;
	constructor(e, t) {
		super(e), this.status = t;
	}
};
async function g(e, t = {}) {
	let n = new Headers(t.headers), r = (t.method || "GET").toUpperCase();
	[
		"GET",
		"HEAD",
		"OPTIONS"
	].includes(r) || n.set("X-HSD-Token", _()), t.body && !(t.body instanceof FormData) && n.set("Content-Type", "application/json");
	let i = ["GET", "HEAD"].includes(r) ? new AbortController() : null, a = () => i?.abort(t.signal?.reason);
	t.signal?.aborted ? a() : t.signal?.addEventListener("abort", a, { once: !0 });
	let o = i ? setTimeout(() => i.abort(), 15e3) : void 0;
	try {
		let r = await fetch(`/api/ribbon${e}`, {
			...t,
			headers: n,
			signal: i?.signal || t.signal,
			credentials: "same-origin",
			cache: "no-store"
		});
		if (!r.ok) {
			let e = `请求失败（${r.status}）`;
			try {
				let t = await r.json();
				e = typeof t.detail == "string" ? t.detail : typeof t.error == "string" ? t.error : JSON.stringify(t.detail || t);
			} catch {}
			throw new h(e, r.status);
		}
		return r.status === 204 ? void 0 : await r.json();
	} catch (e) {
		throw i?.signal.aborted && !t.signal?.aborted ? new h("读取超时，请重试。后台任务不会因此重新提交。", 408) : e;
	} finally {
		clearTimeout(o), t.signal?.removeEventListener("abort", a);
	}
}
var _ = () => "";
function v(e) {
	_ = e;
}
var y = (e, t) => g(e, {
	method: "POST",
	body: JSON.stringify(t)
}), b = (e) => !!e && [
	"QUEUED",
	"RUNNING",
	"RECONCILING"
].includes(e.status), ee = (e) => e.sequence === 0 ? "首稿" : `精修 ${e.sequence}`;
function x(e, t) {
	try {
		return JSON.parse(localStorage.getItem(e) || "null") ?? t;
	} catch {
		return t;
	}
}
function S(e, t) {
	try {
		localStorage.setItem(e, JSON.stringify(t));
	} catch {}
}
// ../../../6dd5/智筛Agent/ribbon_frontend/node_modules/.pnpm/react@19.3.1/node_modules/react/cjs/react-jsx-runtime.production.js
var te = /* @__PURE__ */ e(((e) => {
	var t = Symbol.for("react.transitional.element"), n = Symbol.for("react.fragment");
	function r(e, n, r) {
		var i = null;
		if (r !== void 0 && (i = "" + r), n.key !== void 0 && (i = "" + n.key), "key" in n) for (var a in r = {}, n) a !== "key" && (r[a] = n[a]);
		else r = n;
		return n = r.ref, {
			$$typeof: t,
			type: e,
			key: i,
			ref: n === void 0 ? null : n,
			props: r
		};
	}
	e.Fragment = n, e.jsx = r, e.jsxs = r;
})), C = (/* @__PURE__ */ e(((e, t) => {
	t.exports = te();
})))(), ne = {
	grid: "整齐平铺",
	stagger: "错位平铺",
	scatter: "随机散点",
	single: "单排重复",
	ends: "两端主图",
	panels: "分区拼接",
	bordered: "上下边饰",
	scene: "组合循环",
	fullwidth: "整幅定位",
	alternating: "大小交替",
	ends_open: "两端留白",
	split: "左右分区",
	stacked: "上下分区",
	opposed: "正倒交替"
}, w = /* @__PURE__ */ new Set([
	"grid",
	"stagger",
	"scatter",
	"single",
	"ends",
	"panels"
]), re = {
	design_background: "首稿底纹",
	generate_background: "生成底图",
	plan: "理解修改要求",
	edit_asset: "修改图案",
	edit_background: "修改底纹",
	edit_composite: "修改整幅"
}, T = {
	STARTED: "等待结果",
	SUCCEEDED: "已返回",
	FAILED: "失败",
	UNKNOWN: "结果未确认"
}, E = {
	prepare: "准备",
	provider: "服务响应",
	transport: "网络传输",
	validation: "结果校验",
	complete: "结束",
	recovery: "任务恢复",
	unknown: "历史未记录"
};
function D({ calls: e }) {
	return e?.length ? /* @__PURE__ */ (0, C.jsxs)("details", { children: [/* @__PURE__ */ (0, C.jsxs)("summary", { children: [
		"调用详情（",
		e.length,
		"）"
	] }), /* @__PURE__ */ (0, C.jsx)("ul", { children: e.map((e) => /* @__PURE__ */ (0, C.jsxs)("li", { children: [
		/* @__PURE__ */ (0, C.jsxs)("strong", { children: [
			re[e.operation] || "模型调用",
			" · ",
			T[e.status] || e.status
		] }),
		e.error && /* @__PURE__ */ (0, C.jsx)("small", { children: e.error }),
		e.diagnostic && /* @__PURE__ */ (0, C.jsxs)("small", { children: [
			E[e.diagnostic.stage] || "未知阶段",
			e.diagnostic.http_status && ` · HTTP ${e.diagnostic.http_status}`,
			e.diagnostic.upstream_code && ` · ${e.diagnostic.upstream_code}`
		] }),
		e.request_id && /* @__PURE__ */ (0, C.jsxs)("small", { children: ["请求编号 ", e.request_id] })
	] }, e.id)) })] }) : null;
}
function ie({ onClose: e, onChanged: t }) {
	let [n, r] = (0, l.useState)("tasks"), [i, a] = (0, l.useState)(null), [o, s] = (0, l.useState)(""), [c, u] = (0, l.useState)(""), [d, f] = (0, l.useState)(!1), [p, m] = (0, l.useState)(""), [h, _] = (0, l.useState)(""), [v, b] = (0, l.useState)("grid"), [ee, x] = (0, l.useState)(!0), [S, te] = (0, l.useState)("{}"), [re, T] = (0, l.useState)("演示输出"), [E, ie] = (0, l.useState)(1800), [ae, oe] = (0, l.useState)(300), [se, ce] = (0, l.useState)(150), [ue, de] = (0, l.useState)(!0), fe = /* @__PURE__ */ new Map();
	for (let e of i?.provider_calls ?? []) {
		let t = fe.get(e.job_id);
		t ? t.push(e) : fe.set(e.job_id, [e]);
	}
	async function pe() {
		try {
			a(await g("/admin/overview")), s("");
		} catch (e) {
			s(e instanceof Error ? e.message : "加载失败");
		}
	}
	(0, l.useEffect)(() => {
		pe();
	}, []);
	function me(e) {
		m(e.id), _(e.name), b(e.mode), x(e.enabled), te(JSON.stringify(e.rules, null, 2)), u("保存将建立新的配置版本，历史作品不受影响。");
	}
	async function he(e) {
		e.preventDefault(), f(!0), s("");
		try {
			let e = JSON.parse(S);
			if (!e || Array.isArray(e) || typeof e != "object") throw Error("模板规则必须为 JSON 对象。");
			await y("/admin/templates", {
				...p ? { id: p } : {},
				name: h,
				mode: v,
				enabled: ee,
				rules: e
			}), await Promise.all([pe(), t()]), u("模板新版本已保存，样式图已同步。"), m(""), _(""), te("{}");
		} catch (e) {
			s(e instanceof Error ? e.message : "保存失败");
		} finally {
			f(!1);
		}
	}
	async function ge(e) {
		e.preventDefault(), f(!0), s("");
		try {
			if (E * ae > 4e7) throw Error("总像素不可超过 4000 万。");
			await y("/admin/output-profiles", {
				name: re,
				width: E,
				height: ae,
				dpi: se,
				format: "PNG",
				is_demo: ue
			}), await Promise.all([pe(), t()]), u("新输出配置已启用。已保存的历史版本及其下载文件保持不变。");
		} catch (e) {
			s(e instanceof Error ? e.message : "保存失败");
		} finally {
			f(!1);
		}
	}
	return /* @__PURE__ */ (0, C.jsxs)(le, {
		title: "内部管理",
		onClose: e,
		wide: !0,
		children: [
			/* @__PURE__ */ (0, C.jsx)("div", {
				className: "admin-tabs",
				children: [
					["tasks", "任务查询"],
					["templates", "排版模式"],
					["output", "输出配置"]
				].map(([e, t]) => /* @__PURE__ */ (0, C.jsx)("button", {
					className: n === e ? "active" : "",
					onClick: () => {
						r(e), s(""), u("");
					},
					children: t
				}, e))
			}),
			o && /* @__PURE__ */ (0, C.jsx)("div", {
				className: "notice error",
				role: "alert",
				children: o
			}),
			c && /* @__PURE__ */ (0, C.jsx)("div", {
				className: "notice success",
				role: "status",
				children: c
			}),
			n === "tasks" && /* @__PURE__ */ (0, C.jsxs)(C.Fragment, { children: [
				/* @__PURE__ */ (0, C.jsxs)("div", {
					className: "admin-intro",
					children: [/* @__PURE__ */ (0, C.jsx)("p", { children: "查询后台任务、执行阶段与失败原因。" }), /* @__PURE__ */ (0, C.jsx)("button", {
						className: "secondary small",
						onClick: () => void pe(),
						children: "刷新任务"
					})]
				}),
				/* @__PURE__ */ (0, C.jsxs)("div", {
					className: "table-scroll",
					children: [/* @__PURE__ */ (0, C.jsxs)("table", { children: [/* @__PURE__ */ (0, C.jsx)("thead", { children: /* @__PURE__ */ (0, C.jsxs)("tr", { children: [
						/* @__PURE__ */ (0, C.jsx)("th", { children: "任务" }),
						/* @__PURE__ */ (0, C.jsx)("th", { children: "状态 / 阶段" }),
						/* @__PURE__ */ (0, C.jsx)("th", { children: "提供商" }),
						/* @__PURE__ */ (0, C.jsx)("th", { children: "尝试" }),
						/* @__PURE__ */ (0, C.jsx)("th", { children: "结果 / 错误" })
					] }) }), /* @__PURE__ */ (0, C.jsx)("tbody", { children: i?.jobs.map((e) => /* @__PURE__ */ (0, C.jsxs)("tr", { children: [
						/* @__PURE__ */ (0, C.jsxs)("td", { children: [/* @__PURE__ */ (0, C.jsx)("strong", { children: e.kind }), /* @__PURE__ */ (0, C.jsxs)("small", {
							title: e.id,
							children: [e.id.slice(0, 12), "…"]
						})] }),
						/* @__PURE__ */ (0, C.jsxs)("td", { children: [/* @__PURE__ */ (0, C.jsx)("span", {
							className: `job-status ${e.status.toLowerCase()}`,
							children: e.status
						}), /* @__PURE__ */ (0, C.jsx)("small", { children: e.phase })] }),
						/* @__PURE__ */ (0, C.jsx)("td", { children: e.provider }),
						/* @__PURE__ */ (0, C.jsx)("td", { children: e.attempt }),
						/* @__PURE__ */ (0, C.jsxs)("td", { children: [e.error || e.result_version_id?.slice(0, 12) || e.result_asset_id?.slice(0, 12) || "—", /* @__PURE__ */ (0, C.jsx)(D, { calls: fe.get(e.id) })] })
					] }, e.id)) })] }), !i?.jobs.length && /* @__PURE__ */ (0, C.jsx)("div", {
						className: "empty-library",
						children: "暂无后台任务"
					})]
				}),
				/* @__PURE__ */ (0, C.jsx)("p", {
					className: "microcopy",
					children: "素材维护：在工作台素材库中上传或移除；勾选“共享素材”后可供所有账号使用。"
				})
			] }),
			n === "templates" && /* @__PURE__ */ (0, C.jsxs)("div", {
				className: "admin-columns",
				children: [/* @__PURE__ */ (0, C.jsxs)("div", {
					className: "admin-existing",
					children: [/* @__PURE__ */ (0, C.jsx)("h3", { children: "已有模式" }), i?.templates.map((e) => /* @__PURE__ */ (0, C.jsxs)("button", {
						className: `admin-template ${p === e.id ? "selected" : ""}`,
						onClick: () => me(e),
						children: [
							/* @__PURE__ */ (0, C.jsx)("img", {
								src: e.thumbnail_url,
								alt: e.name
							}),
							/* @__PURE__ */ (0, C.jsxs)("div", { children: [/* @__PURE__ */ (0, C.jsx)("strong", { children: e.name }), /* @__PURE__ */ (0, C.jsxs)("small", { children: [
								"版本 ",
								e.version,
								" · ",
								e.enabled ? "已启用" : "已停用"
							] })] }),
							/* @__PURE__ */ (0, C.jsx)(O, {
								name: "arrow",
								size: 15
							})
						]
					}, `${e.id}-${e.version}`))]
				}), /* @__PURE__ */ (0, C.jsxs)("form", {
					onSubmit: he,
					className: "admin-form",
					children: [
						/* @__PURE__ */ (0, C.jsx)("h3", { children: p ? "创建模式新版本" : "新增排版模式" }),
						/* @__PURE__ */ (0, C.jsxs)("label", { children: ["模式名称", /* @__PURE__ */ (0, C.jsx)("input", {
							value: h,
							onChange: (e) => _(e.target.value),
							maxLength: 60,
							required: !0
						})] }),
						/* @__PURE__ */ (0, C.jsxs)("label", { children: ["排版规则类型", /* @__PURE__ */ (0, C.jsx)("select", {
							value: v,
							onChange: (e) => b(e.target.value),
							children: Object.entries(ne).map(([e, t]) => /* @__PURE__ */ (0, C.jsx)("option", {
								value: e,
								children: t
							}, e))
						})] }),
						/* @__PURE__ */ (0, C.jsxs)("label", { children: ["规则配置（JSON）", /* @__PURE__ */ (0, C.jsx)("textarea", {
							className: "code-input",
							value: S,
							onChange: (e) => te(e.target.value),
							rows: 5
						})] }),
						/* @__PURE__ */ (0, C.jsxs)("small", {
							className: "template-rules-help",
							children: [w.has(v) ? "支持 rows（1–4）、step_ratio（0.2–2）、motif_ratio（0.05–0.8）。" : v === "fullwidth" || v === "ends_open" ? "仅支持 motif_ratio（0.05–0.8）调整图案大小；行数固定，不使用 rows 或 step_ratio。" : "支持 step_ratio（0.2–2）、motif_ratio（0.05–0.8）；行数由排法固定，不使用 rows。", "服务端会检查，不适用的字段请移除。"]
						}),
						/* @__PURE__ */ (0, C.jsxs)("label", {
							className: "checkbox-line",
							children: [/* @__PURE__ */ (0, C.jsx)("input", {
								type: "checkbox",
								checked: ee,
								onChange: (e) => x(e.target.checked)
							}), "启用此模式"]
						}),
						/* @__PURE__ */ (0, C.jsx)("button", {
							className: "primary",
							disabled: d,
							children: d ? "保存中…" : "保存新版本"
						}),
						p && /* @__PURE__ */ (0, C.jsx)("button", {
							type: "button",
							className: "text-button",
							onClick: () => {
								m(""), _(""), te("{}"), x(!0);
							},
							children: "改为新增模式"
						})
					]
				})]
			}),
			n === "output" && /* @__PURE__ */ (0, C.jsxs)("div", {
				className: "admin-columns",
				children: [/* @__PURE__ */ (0, C.jsxs)("div", {
					className: "admin-existing",
					children: [
						/* @__PURE__ */ (0, C.jsx)("h3", { children: "配置版本" }),
						/* @__PURE__ */ (0, C.jsx)("p", {
							className: "microcopy",
							children: "固定输出规格只在内部维护。每个作品版本会保存使用的配置快照。"
						}),
						i?.output_profiles.map((e) => /* @__PURE__ */ (0, C.jsxs)("div", {
							className: "profile-item",
							children: [
								/* @__PURE__ */ (0, C.jsxs)("strong", { children: [e.name, /* @__PURE__ */ (0, C.jsxs)("span", {
									className: "tiny-pill",
									children: ["V", e.version]
								})] }),
								/* @__PURE__ */ (0, C.jsxs)("small", { children: [
									e.width,
									" × ",
									e.height,
									" px · ",
									e.dpi,
									" DPI · PNG"
								] }),
								/* @__PURE__ */ (0, C.jsx)("span", { children: e.is_demo ? "演示配置，未完成业务验收" : "正式配置标记（仍需接收软件验收）" })
							]
						}, `${e.id}-${e.version}`))
					]
				}), /* @__PURE__ */ (0, C.jsxs)("form", {
					className: "admin-form",
					onSubmit: ge,
					children: [
						/* @__PURE__ */ (0, C.jsx)("h3", { children: "启用新的输出配置" }),
						/* @__PURE__ */ (0, C.jsxs)("label", { children: ["配置名称", /* @__PURE__ */ (0, C.jsx)("input", {
							value: re,
							onChange: (e) => T(e.target.value),
							required: !0,
							maxLength: 60
						})] }),
						/* @__PURE__ */ (0, C.jsxs)("div", {
							className: "form-two",
							children: [/* @__PURE__ */ (0, C.jsxs)("label", { children: ["宽度（px）", /* @__PURE__ */ (0, C.jsx)("input", {
								type: "number",
								min: 64,
								max: 16e3,
								value: E,
								onChange: (e) => ie(Number(e.target.value)),
								required: !0
							})] }), /* @__PURE__ */ (0, C.jsxs)("label", { children: ["高度（px）", /* @__PURE__ */ (0, C.jsx)("input", {
								type: "number",
								min: 64,
								max: 5e3,
								value: ae,
								onChange: (e) => oe(Number(e.target.value)),
								required: !0
							})] })]
						}),
						/* @__PURE__ */ (0, C.jsxs)("label", { children: ["DPI", /* @__PURE__ */ (0, C.jsx)("input", {
							type: "number",
							min: 72,
							max: 1200,
							value: se,
							onChange: (e) => ce(Number(e.target.value)),
							required: !0
						})] }),
						/* @__PURE__ */ (0, C.jsxs)("label", {
							className: "checkbox-line",
							children: [/* @__PURE__ */ (0, C.jsx)("input", {
								type: "checkbox",
								checked: ue,
								onChange: (e) => de(e.target.checked)
							}), "演示配置"]
						}),
						/* @__PURE__ */ (0, C.jsx)("p", {
							className: "microcopy",
							children: "当前支持 PNG。正式数值以公司现用文件为准；取消演示标记不代表业务输出已经验收。"
						}),
						/* @__PURE__ */ (0, C.jsx)("button", {
							className: "primary",
							disabled: d,
							children: d ? "保存中…" : "保存并启用新版本"
						})
					]
				})]
			})
		]
	});
}
// src/LayoutExamples.tsx
function ae({ url: e, title: t }) {
	let [n, r] = (0, l.useState)(!1), [i, a] = (0, l.useState)(0), o = /^\/static\/ribbon\/layout-v3\/[a-z]+(?:_[a-z]+)*(?:-\d+)?\.webp(?:\?v=[a-z0-9]+)?$/.test(e);
	return (0, l.useEffect)(() => {
		r(!1), a(0);
	}, [e]), !o || n ? /* @__PURE__ */ (0, C.jsxs)("div", {
		className: "layout-example-unavailable",
		children: [/* @__PURE__ */ (0, C.jsx)("p", { children: "程序示例暂未加载。" }), o && /* @__PURE__ */ (0, C.jsx)("button", {
			className: "secondary small",
			onClick: () => {
				r(!1), a((e) => e + 1);
			},
			children: "重试示例"
		})]
	}) : /* @__PURE__ */ (0, C.jsx)("img", {
		src: e,
		alt: t,
		loading: "lazy",
		decoding: "async",
		onError: () => r(!0)
	}, `${e}-${i}`);
}
function oe(e) {
	if (!e?.startsWith("/api/ribbon/layout-examples/")) return null;
	try {
		let t = new URL(e, location.href);
		return t.origin === location.origin && t.pathname.endsWith("/image") ? t.href : null;
	} catch {
		return null;
	}
}
function se({ example: e }) {
	let [t, n] = (0, l.useState)(!1), [r, i] = (0, l.useState)(!1), [a, o] = (0, l.useState)(0), s = (0, l.useRef)(null), c = e.available ? oe(e.image_url) : null;
	return (0, l.useEffect)(() => {
		i(!1), n(!1), o(0);
	}, [
		e.id,
		e.image_url,
		e.available
	]), !c || r ? /* @__PURE__ */ (0, C.jsxs)("div", {
		className: "layout-example-unavailable",
		role: "status",
		children: [/* @__PURE__ */ (0, C.jsx)("p", { children: r ? "案例图片没有加载成功，排版说明仍可查看。" : "这张案例图暂未加载，排版说明仍可查看。" }), c && /* @__PURE__ */ (0, C.jsx)("button", {
			type: "button",
			className: "secondary",
			onClick: () => {
				i(!1), o((e) => e + 1);
			},
			children: "重试图片"
		})]
	}) : /* @__PURE__ */ (0, C.jsxs)(C.Fragment, { children: [/* @__PURE__ */ (0, C.jsxs)("div", {
		className: "layout-example-image-tools",
		children: [/* @__PURE__ */ (0, C.jsx)("button", {
			type: "button",
			className: "text-button",
			"aria-pressed": t,
			"aria-label": `${t ? "查看整条" : "放大查看"} ${e.code}`,
			onClick: () => {
				n((e) => !e), s.current && (s.current.scrollLeft = 0);
			},
			children: t ? "查看整条" : "放大查看"
		}), t && /* @__PURE__ */ (0, C.jsx)("span", { children: "可左右滚动查看" })]
	}), /* @__PURE__ */ (0, C.jsx)("div", {
		ref: s,
		className: `layout-example-viewport${t ? " is-zoomed" : ""}`,
		role: "region",
		"aria-label": `${e.code} 案例图${t ? "，可左右滚动" : ""}`,
		tabIndex: t ? 0 : -1,
		style: { "--example-width": `${e.width}px` },
		children: /* @__PURE__ */ (0, C.jsx)("img", {
			src: c,
			width: e.width,
			height: e.height,
			alt: `${e.title}，图库图号 ${e.code}`,
			loading: "lazy",
			decoding: "async",
			referrerPolicy: "same-origin",
			onError: () => i(!0)
		}, `${e.id}-${e.image_url}-${a}`)
	})] });
}
function ce({ mode: e, cache: t, onUnauthorized: n, onViewAll: r, referenceMode: i, onChooseReference: a, legacyLayout: o = !1 }) {
	let [s, c] = (0, l.useState)(() => t.current), [u, f] = (0, l.useState)(!t.current), [p, m] = (0, l.useState)(""), [_, v] = (0, l.useState)(0), y = (0, l.useRef)(n);
	y.current = n;
	let b = (0, l.useRef)(null), [ee, x] = (0, l.useState)(0), [S, te] = (0, l.useState)(""), [ne, w] = (0, l.useState)("company");
	(0, l.useEffect)(() => {
		if (t.current) {
			c(t.current), f(!1);
			return;
		}
		let e = new AbortController(), n = !1;
		return f(!0), m(""), g("/layout-examples", { signal: e.signal }).then((e) => {
			n || (t.current = e, c(e));
		}).catch((e) => {
			n || (m(e instanceof Error ? e.message : "请稍后重新加载案例。"), e instanceof h && e.status === 401 && y.current());
		}).finally(() => {
			n || f(!1);
		}), () => {
			n = !0, e.abort();
		};
	}, [t, _]), (0, l.useEffect)(() => {
		b.current?.closest(".modal")?.scrollTo({ top: 0 }), x(0), te(""), w("company");
	}, [e]);
	function re() {
		t.current = null, c(null), v((e) => e + 1);
	}
	if (u) return /* @__PURE__ */ (0, C.jsxs)("div", {
		className: "layout-examples-loading",
		role: "status",
		children: [/* @__PURE__ */ (0, C.jsx)("span", { className: "spinner" }), "正在加载排版案例…"]
	});
	if (p || !s) return /* @__PURE__ */ (0, C.jsxs)("div", {
		className: "layout-examples-error",
		role: "alert",
		children: [/* @__PURE__ */ (0, C.jsxs)("p", { children: ["案例暂时无法打开：", p || "请稍后再试。"] }), /* @__PURE__ */ (0, C.jsx)("button", {
			type: "button",
			className: "secondary",
			onClick: re,
			children: "重新加载案例"
		})]
	});
	let T = e || S, E = s.modes.find((e) => e.mode === T), D = T ? (E?.example_ids || []).flatMap((e) => s.examples.filter((t) => t.id === e)) : s.examples, ie = Math.min(ee, Math.max(0, D.length - 1)), ce = T ? D.slice(ie, ie + 1) : D;
	return /* @__PURE__ */ (0, C.jsxs)("div", {
		className: "layout-examples",
		ref: b,
		children: [
			/* @__PURE__ */ (0, C.jsxs)("div", {
				className: "layout-examples-intro",
				children: [
					E && /* @__PURE__ */ (0, C.jsx)("p", {
						className: "layout-mode-summary",
						children: E.summary
					}),
					E?.note && /* @__PURE__ */ (0, C.jsx)("p", {
						className: "layout-mode-note",
						children: E.note
					}),
					!e && /* @__PURE__ */ (0, C.jsx)("p", {
						className: "layout-mode-summary",
						children: a ? "案例可查看，也可明确选择为 AI 首稿参考。只有与当前排法匹配的可用案例可以选中。" : "先看排列方式，再选择适合的排版。案例只说明结构，生成时使用你自己选择的素材。"
					}),
					a && /* @__PURE__ */ (0, C.jsx)("p", {
						className: "layout-reference-help",
						children: "查看不会发送案例。只有明确选为参考后，生成 AI 首稿时才把所选案例发送给 Seedream。"
					}),
					e && !E && /* @__PURE__ */ (0, C.jsx)("p", { children: "当前排版暂无对应的公司案例，可先查看其他排法。" }),
					/* @__PURE__ */ (0, C.jsxs)("div", {
						className: "layout-examples-tools",
						children: [
							e && /* @__PURE__ */ (0, C.jsx)("button", {
								type: "button",
								className: "secondary",
								onClick: r,
								children: "查看全部案例"
							}),
							!e && /* @__PURE__ */ (0, C.jsxs)("label", {
								className: "case-mode-filter",
								children: ["排版", /* @__PURE__ */ (0, C.jsxs)("select", {
									"aria-label": "筛选排版案例",
									value: S,
									onChange: (e) => {
										te(e.target.value), x(0), w("company");
									},
									children: [/* @__PURE__ */ (0, C.jsx)("option", {
										value: "",
										children: "全部"
									}), s.modes.map((e) => /* @__PURE__ */ (0, C.jsx)("option", {
										value: e.mode,
										children: e.name
									}, e.mode))]
								})]
							}),
							/* @__PURE__ */ (0, C.jsx)("button", {
								type: "button",
								className: "text-button",
								onClick: re,
								children: "重新加载"
							})
						]
					})
				]
			}),
			E?.demo_variants?.length ? /* @__PURE__ */ (0, C.jsxs)("div", {
				className: "layout-example-kind",
				role: "group",
				"aria-label": "参考类型",
				children: [/* @__PURE__ */ (0, C.jsxs)("button", {
					className: ne === "company" ? "selected" : "",
					"aria-pressed": ne === "company",
					onClick: () => w("company"),
					children: [
						"公司案例（",
						D.length,
						"）"
					]
				}), /* @__PURE__ */ (0, C.jsxs)("button", {
					className: ne === "demo" ? "selected" : "",
					"aria-pressed": ne === "demo",
					onClick: () => w("demo"),
					children: [
						"程序示例（",
						E.demo_variants.length,
						"）"
					]
				})]
			}) : null,
			ne === "demo" && E ? /* @__PURE__ */ (0, C.jsxs)("div", {
				className: "layout-demos",
				children: [
					/* @__PURE__ */ (0, C.jsx)("p", {
						className: "layout-demo-note",
						children: "以下用自制素材实际排版，说明素材数量与角色怎样影响结果，不是公司原稿或 AI 生图。"
					}),
					o && /* @__PURE__ */ (0, C.jsx)("p", {
						className: "layout-demo-note",
						children: "程序示例展示新版排法。当前旧作品继续使用原排版规则，新建作品才会使用新版。"
					}),
					(E.demo_variants || []).map((e) => /* @__PURE__ */ (0, C.jsxs)("figure", { children: [/* @__PURE__ */ (0, C.jsxs)("figcaption", { children: [/* @__PURE__ */ (0, C.jsx)("strong", { children: e.title }), /* @__PURE__ */ (0, C.jsx)("span", { children: e.description })] }), /* @__PURE__ */ (0, C.jsx)(ae, {
						url: e.image_url,
						title: e.title
					})] }, e.id))
				]
			}) : /* @__PURE__ */ (0, C.jsxs)(C.Fragment, { children: [
				T && D.length > 1 && /* @__PURE__ */ (0, C.jsxs)("nav", {
					className: "layout-case-navigation",
					"aria-label": "本排法案例",
					children: [
						/* @__PURE__ */ (0, C.jsx)("button", {
							className: "secondary small",
							disabled: ie === 0,
							onClick: () => x(ie - 1),
							children: "上一例"
						}),
						/* @__PURE__ */ (0, C.jsxs)("label", { children: [/* @__PURE__ */ (0, C.jsxs)("span", { children: [
							"案例 ",
							ie + 1,
							" / ",
							D.length
						] }), /* @__PURE__ */ (0, C.jsx)("select", {
							"aria-label": "选择案例",
							value: D[ie].id,
							onChange: (e) => x(D.findIndex((t) => t.id === e.target.value)),
							children: D.map((e, t) => /* @__PURE__ */ (0, C.jsxs)("option", {
								value: e.id,
								children: [
									t + 1,
									". ",
									e.title
								]
							}, e.id))
						})] }),
						/* @__PURE__ */ (0, C.jsx)("button", {
							className: "secondary small",
							disabled: ie === D.length - 1,
							onClick: () => x(ie + 1),
							children: "下一例"
						})
					]
				}),
				/* @__PURE__ */ (0, C.jsx)("div", {
					className: "layout-examples-list",
					children: ce.map((e) => {
						let t = T ? e.mode_notes?.[T] : void 0;
						return /* @__PURE__ */ (0, C.jsxs)("article", {
							className: "layout-example",
							children: [
								/* @__PURE__ */ (0, C.jsxs)("div", {
									className: "layout-example-heading",
									children: [/* @__PURE__ */ (0, C.jsx)("h3", { children: e.title }), /* @__PURE__ */ (0, C.jsxs)("div", { children: [
										e.reference_only && /* @__PURE__ */ (0, C.jsx)("span", {
											className: "layout-reference-tag",
											children: "延展参考"
										}),
										t?.fit === "partial" && /* @__PURE__ */ (0, C.jsx)("span", {
											className: "layout-reference-tag",
											children: "组合参考"
										}),
										/* @__PURE__ */ (0, C.jsx)("span", {
											className: "layout-example-code",
											children: e.code
										})
									] })]
								}),
								/* @__PURE__ */ (0, C.jsx)("p", {
									className: "layout-example-description",
									children: e.description
								}),
								!T && s.modes.filter((t) => t.example_ids.includes(e.id)).map((e) => /* @__PURE__ */ (0, C.jsxs)("p", {
									className: "layout-mode-note",
									children: [/* @__PURE__ */ (0, C.jsxs)("strong", { children: [e.name, "："] }), e.note]
								}, e.mode)),
								/* @__PURE__ */ (0, C.jsx)(se, { example: e }),
								/* @__PURE__ */ (0, C.jsxs)("p", {
									className: "layout-example-look",
									children: [/* @__PURE__ */ (0, C.jsx)("strong", { children: "看点：" }), t?.look_for || (Array.isArray(e.look_for) ? e.look_for.join("；") : e.look_for)]
								}),
								t?.difference && /* @__PURE__ */ (0, C.jsxs)("p", {
									className: "layout-example-difference",
									children: [/* @__PURE__ */ (0, C.jsx)("strong", { children: "与当前排法的区别：" }), t.difference]
								}),
								e.reference_only && /* @__PURE__ */ (0, C.jsx)("p", {
									className: "layout-example-reference",
									children: "当前没有单独的对应排版选项，不会因查看案例自动生成这种效果。"
								}),
								a && i && d(e, i) && oe(e.image_url) && /* @__PURE__ */ (0, C.jsx)("button", {
									type: "button",
									className: "secondary choose-ai-reference",
									onClick: () => a(e),
									children: "用于AI首稿参考"
								})
							]
						}, e.id);
					})
				}),
				!D.length && /* @__PURE__ */ (0, C.jsx)("p", {
					className: "layout-example-unavailable",
					children: "暂时没有对应案例，请查看全部案例或稍后重新加载。"
				})
			] }),
			/* @__PURE__ */ (0, C.jsxs)("p", {
				className: "layout-examples-source",
				children: [
					s.source_name,
					" · ",
					s.note
				]
			})
		]
	});
}
// src/App.tsx
function O({ name: e, size: t = 18 }) {
	return /* @__PURE__ */ (0, C.jsx)("svg", {
		width: t,
		height: t,
		viewBox: "0 0 24 24",
		fill: "none",
		stroke: "currentColor",
		strokeWidth: "1.65",
		strokeLinecap: "round",
		strokeLinejoin: "round",
		"aria-hidden": "true",
		children: {
			spark: /* @__PURE__ */ (0, C.jsxs)(C.Fragment, { children: [/* @__PURE__ */ (0, C.jsx)("path", { d: "m12 3 2.3 6.7L21 12l-6.7 2.3L12 21l-2.3-6.7L3 12l6.7-2.3Z" }), /* @__PURE__ */ (0, C.jsx)("path", { d: "m20 2 .7 2.3L23 5l-2.3.7L20 8l-.7-2.3L17 5l2.3-.7Z" })] }),
			upload: /* @__PURE__ */ (0, C.jsx)(C.Fragment, { children: /* @__PURE__ */ (0, C.jsx)("path", { d: "M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6" }) }),
			grid: /* @__PURE__ */ (0, C.jsxs)(C.Fragment, { children: [
				/* @__PURE__ */ (0, C.jsx)("rect", {
					x: "3",
					y: "3",
					width: "7",
					height: "7",
					rx: "1"
				}),
				/* @__PURE__ */ (0, C.jsx)("rect", {
					x: "14",
					y: "3",
					width: "7",
					height: "7",
					rx: "1"
				}),
				/* @__PURE__ */ (0, C.jsx)("rect", {
					x: "3",
					y: "14",
					width: "7",
					height: "7",
					rx: "1"
				}),
				/* @__PURE__ */ (0, C.jsx)("rect", {
					x: "14",
					y: "14",
					width: "7",
					height: "7",
					rx: "1"
				})
			] }),
			back: /* @__PURE__ */ (0, C.jsx)(C.Fragment, { children: /* @__PURE__ */ (0, C.jsx)("path", { d: "m8 4-5 5 5 5M3 9h10a7 7 0 0 1 0 14" }) }),
			download: /* @__PURE__ */ (0, C.jsx)(C.Fragment, { children: /* @__PURE__ */ (0, C.jsx)("path", { d: "M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4" }) }),
			plus: /* @__PURE__ */ (0, C.jsx)("path", { d: "M12 4v16M4 12h16" }),
			close: /* @__PURE__ */ (0, C.jsx)("path", { d: "m6 6 12 12M6 18 18 6" }),
			check: /* @__PURE__ */ (0, C.jsx)("path", { d: "m4 12 5 5L20 6" }),
			folder: /* @__PURE__ */ (0, C.jsx)("path", { d: "M3 6h7l2 3h9v11H3ZM3 6V4h7l2 2" }),
			arrow: /* @__PURE__ */ (0, C.jsx)("path", { d: "M4 12h16m-6-6 6 6-6 6" }),
			logout: /* @__PURE__ */ (0, C.jsx)(C.Fragment, { children: /* @__PURE__ */ (0, C.jsx)("path", { d: "M9 4H3v16h6m5-13 5 5-5 5M8 12h11" }) }),
			settings: /* @__PURE__ */ (0, C.jsxs)(C.Fragment, { children: [/* @__PURE__ */ (0, C.jsx)("circle", {
				cx: "12",
				cy: "12",
				r: "4"
			}), /* @__PURE__ */ (0, C.jsx)("path", { d: "m12 2 2 3 4-1 1 4 3 2-2 3 1 4-4 1-2 3-3-2-4 1-1-4-3-2 2-3-1-4 4-1Z" })] })
		}[e]
	});
}
function le({ title: e, children: t, onClose: n, wide: r = !1, className: i = "" }) {
	let a = (0, l.useRef)(null);
	return (0, l.useEffect)(() => {
		let e = a.current?.getRootNode(), t = e?.activeElement;
		(a.current?.querySelector("button,input,select,textarea"))?.focus();
		let r = (t) => {
			if (t.key === "Escape" && n(), t.key === "Tab") {
				let n = a.current?.querySelectorAll("button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href],[tabindex=\"0\"]");
				if (!n?.length) return;
				let r = n[0], i = n[n.length - 1];
				t.shiftKey && e?.activeElement === r ? (t.preventDefault(), i.focus()) : !t.shiftKey && e?.activeElement === i && (t.preventDefault(), r.focus());
			}
		};
		document.addEventListener("keydown", r);
		let i = document.body.style.overflow;
		return document.body.style.overflow = "hidden", () => {
			document.removeEventListener("keydown", r), document.body.style.overflow = i, t?.focus();
		};
	}, []), /* @__PURE__ */ (0, C.jsx)("div", {
		className: "modal-scrim",
		onMouseDown: (e) => {
			e.target === e.currentTarget && n();
		},
		children: /* @__PURE__ */ (0, C.jsxs)("div", {
			ref: a,
			className: `modal ${r ? "modal-wide" : ""} ${i}`,
			role: "dialog",
			"aria-modal": "true",
			"aria-label": e,
			children: [/* @__PURE__ */ (0, C.jsxs)("div", {
				className: "modal-heading",
				children: [/* @__PURE__ */ (0, C.jsx)("div", { children: /* @__PURE__ */ (0, C.jsx)("h2", { children: e }) }), /* @__PURE__ */ (0, C.jsx)("button", {
					className: "icon-button",
					"aria-label": "关闭弹窗",
					onClick: n,
					children: /* @__PURE__ */ (0, C.jsx)(O, { name: "close" })
				})]
			}), t]
		})
	});
}
function ue() {
	return /* @__PURE__ */ (0, C.jsxs)("div", {
		className: "brand",
		children: [/* @__PURE__ */ (0, C.jsx)("span", {
			className: "brand-icon",
			children: /* @__PURE__ */ (0, C.jsxs)("svg", {
				width: "26",
				height: "30",
				viewBox: "0 0 26 30",
				fill: "none",
				children: [/* @__PURE__ */ (0, C.jsx)("path", {
					d: "M5 3h16v12L13 9 5 15V3Z",
					fill: "currentColor"
				}), /* @__PURE__ */ (0, C.jsx)("path", {
					d: "M5 19v8l8-5 8 5V16l-8-5-8 5",
					stroke: "currentColor",
					strokeWidth: "2"
				})]
			})
		}), /* @__PURE__ */ (0, C.jsx)("div", { children: /* @__PURE__ */ (0, C.jsx)("strong", { children: "丝带设计助手" }) })]
	});
}
function de(e) {
	return e instanceof Error ? e.message : "发生未知错误，请重试。";
}
var fe = {
	asset_ids: [],
	background_id: "",
	template_id: "",
	background_tone: "soft",
	design_density: "balanced"
}, pe = /* @__PURE__ */ new Set([
	"grid",
	"stagger",
	"scatter",
	"single",
	"ends",
	"panels"
]), me = {
	grid: "完整图案按行排列，保持比例；可用画面密度选择疏朗或饱满。",
	stagger: "相邻行错开，整组图案连续重复；文字和装饰作为一个整体保留。",
	scatter: "轻微错落排列，默认保持图案朝向；不会自动拆出小装饰。",
	single: "适合文字或较大的主体，多个图案按选择顺序整组重复。",
	bordered: "第一个图案放中间，其余图案做上下边饰；至少选择 2 个图案。",
	scene: "第一个图案作主图，其余稍小、底部对齐，再整组循环；辅助装饰需自行选入。",
	fullwidth: "只选 1 张完整设计，保持比例；循环作品会将整幅作为一个单元重复。",
	alternating: "图案一大一小依次重复，可选择 1–12 个图案。",
	ends_open: "选 1–2 个图案放在两端，中间留白；循环作品会将两端与留白作为完整面板重复。",
	split: "至少选择 2 个图案，前半组放左侧，后半组放右侧。",
	stacked: "至少选择 2 个图案，前半组放上方，后半组放下方。",
	opposed: "相邻图案正向、倒置交替，旋转 180°，不会镜像翻字。"
}, he = {
	left: "左区",
	center: "中区",
	right: "右区",
	top: "上区",
	bottom: "下区"
}, ge = {
	panels: [
		"left",
		"center",
		"right"
	],
	split: ["left", "right"],
	stacked: ["top", "bottom"]
}, _e = {
	scene: "选择主图、配角和小点缀，按角色组成场景；完整人物和文字不拆开。",
	scatter: "主图错落倾斜，小点缀填入空隙；不会自动把人物缩成配饰。",
	bordered: "主图排在中间。需要小图沿上下边排列时，将它设为上下边饰，也可另选完整边饰条。"
}, ve = {
	scatter: "完整图案以不同角度和大小错落分布，整个单元循环。",
	bordered: "中央重复主图，上下为连续边线，可选独立边饰。",
	panels: "左、中、右三区各自排放图案，可分别选择底纹。"
};
function ye(e, t, n = !1) {
	return t ? e === "fullwidth" && t !== 1 ? "整幅定位只使用 1 个完整图案，请移除多余图案。" : e === "ends_open" && t > 2 ? "两端留白最多使用 2 个图案，请保留 1–2 个。" : e && (!n && e === "bordered" || ["split", "stacked"].includes(e)) && t < 2 ? "这类排版至少需要 2 个图案，请再选择一个。" : "" : "";
}
function be(e, t) {
	return {
		asset_ids: [
			"demo-flower",
			"demo-star",
			"demo-ring"
		].filter((t) => e.some((e) => e.id === t)),
		background_id: e.find((e) => e.id === "demo-bg-sage")?.id || "",
		background_tone: "soft",
		design_density: "balanced",
		template_id: t.find((e) => e.mode === "stagger" && e.enabled)?.id || t.find((e) => e.enabled)?.id || ""
	};
}
function xe(e, t) {
	let n = t?.snapshot, r = !t || [
		"design-rhythm-v1",
		"design-rhythm-v2",
		"seamless-unit-v1",
		"seamless-unit-v2",
		"seamless-unit-v3"
	].includes(n?.layout_engine || ""), i = {
		...e,
		background_tone: e.background_tone ?? n?.background_tone ?? (r ? "soft" : "original")
	};
	return t && !["seamless-unit-v2", "seamless-unit-v3"].includes(n?.layout_engine || "") && (delete i.zone_background_refs, delete i.border_ref), t && n?.layout_engine !== "seamless-unit-v3" && delete i.pattern_roles, r ? i.design_density = e.design_density ?? n?.design_density ?? "balanced" : delete i.design_density, i;
}
function k({ version: e, target: t }) {
	let n = e.snapshot.loop;
	if (t === "layout" || !t) return null;
	let { width: r, height: i } = n, a = ge[e.snapshot.template_mode] || [], o = a.indexOf(t.slice(5)), s = [], c = (t) => e.snapshot.template_mode === "stacked" ? [[
		0,
		t * i / a.length,
		r,
		i / a.length
	]] : [[
		t * r / a.length,
		0,
		r / a.length,
		i
	]];
	if (t === "background") s = a.length ? a.flatMap((t, n) => e.snapshot.zone_background_refs?.[t] || e.snapshot.zone_colors?.[t] ? [] : c(n)) : [[
		0,
		0,
		r,
		i
	]];
	else if (t === "border") s = [[
		0,
		.08 * i,
		r,
		.115 * i
	], [
		0,
		.805 * i,
		r,
		.115 * i
	]];
	else if (t.startsWith("zone:") && o >= 0) s = c(o);
	else for (let n of e.snapshot.object_transforms || []) {
		if (n.slot_id !== t) continue;
		let e = n.x - n.width / 2, i = n.y - n.height / 2;
		s.push([
			e,
			i,
			n.width,
			n.height
		]), e < 0 && s.push([
			e + r,
			i,
			n.width,
			n.height
		]), e + n.width > r && s.push([
			e - r,
			i,
			n.width,
			n.height
		]);
	}
	return /* @__PURE__ */ (0, C.jsx)("svg", {
		className: "target-overlay",
		viewBox: `0 0 ${r} ${i}`,
		"aria-label": "精修范围",
		children: s.map(([e, t, n, r], i) => /* @__PURE__ */ (0, C.jsx)("rect", {
			x: e,
			y: t,
			width: n,
			height: r,
			vectorEffect: "non-scaling-stroke"
		}, i))
	});
}
function A({ version: e, sizeLabel: t, target: n }) {
	let [r, i] = (0, l.useState)(!1), [a, o] = (0, l.useState)(!1), s = e.snapshot.loop, c = e.snapshot.output_profile_source;
	return /* @__PURE__ */ (0, C.jsxs)("div", {
		className: "loop-preview",
		children: [
			/* @__PURE__ */ (0, C.jsxs)("div", {
				className: "loop-view-heading",
				children: [/* @__PURE__ */ (0, C.jsx)("strong", { children: r ? "连续效果预览" : "循环单元" }), /* @__PURE__ */ (0, C.jsx)("span", { children: r ? "同一单元横向重复 3 次" : t })]
			}),
			/* @__PURE__ */ (0, C.jsx)("div", {
				className: "loop-unit-view",
				hidden: r,
				children: /* @__PURE__ */ (0, C.jsxs)("div", {
					className: "target-layer",
					children: [/* @__PURE__ */ (0, C.jsx)(Se, {
						src: e.preview_url,
						decoding: "async",
						alt: `${ee(e)}的循环单元预览`
					}), !r && /* @__PURE__ */ (0, C.jsx)(k, {
						version: e,
						target: n
					})]
				})
			}),
			/* @__PURE__ */ (0, C.jsx)("div", {
				className: "loop-continuity",
				hidden: !r,
				children: /* @__PURE__ */ (0, C.jsx)("div", {
					className: `loop-continuity-track ${a ? "show-seams" : ""}`,
					children: [
						0,
						1,
						2
					].map((t) => /* @__PURE__ */ (0, C.jsxs)("div", {
						className: "loop-repeat",
						children: [/* @__PURE__ */ (0, C.jsx)(Se, {
							src: e.preview_url,
							decoding: "async",
							alt: t === 0 ? `${ee(e)}的三次连续效果预览` : ""
						}), r && /* @__PURE__ */ (0, C.jsx)(k, {
							version: e,
							target: n
						})]
					}, t))
				})
			}),
			/* @__PURE__ */ (0, C.jsxs)("div", {
				className: "loop-preview-tools",
				children: [/* @__PURE__ */ (0, C.jsx)("button", {
					type: "button",
					className: "loop-view-button",
					"aria-pressed": r,
					onClick: () => i((e) => !e),
					children: r ? "返回循环单元" : "查看连续效果"
				}), r && /* @__PURE__ */ (0, C.jsxs)("label", {
					className: "loop-seam-toggle",
					children: [/* @__PURE__ */ (0, C.jsx)("input", {
						type: "checkbox",
						checked: a,
						onChange: (e) => o(e.target.checked)
					}), "显示接缝位置"]
				})]
			}),
			s.status === "needs_review" && /* @__PURE__ */ (0, C.jsxs)("div", {
				className: "loop-check needs-review",
				children: [/* @__PURE__ */ (0, C.jsx)("strong", { children: "接缝提示" }), !!s.issues?.length && /* @__PURE__ */ (0, C.jsx)("ul", {
					"aria-label": "循环检查提示",
					children: s.issues.map((e, t) => /* @__PURE__ */ (0, C.jsx)("li", {
						className: e.severity,
						children: e.message
					}, `${e.code}:${t}`))
				})]
			}),
			s.mode_notice && /* @__PURE__ */ (0, C.jsx)("p", {
				className: "loop-mode-notice",
				children: s.mode_notice
			}),
			!!s.motif_resolution?.note && /* @__PURE__ */ (0, C.jsx)("p", {
				className: "loop-resolution-note",
				children: s.motif_resolution.note
			}),
			/* @__PURE__ */ (0, C.jsxs)("details", {
				className: "loop-technical-details",
				children: [
					/* @__PURE__ */ (0, C.jsx)("summary", { children: "输出详情" }),
					s.status === "checked" && /* @__PURE__ */ (0, C.jsx)("strong", { children: "工程循环检查通过" }),
					/* @__PURE__ */ (0, C.jsx)("p", { children: "下载为一个原尺寸循环单元。工程检查只核对排版和接缝，印刷效果需另行核样。" }),
					/* @__PURE__ */ (0, C.jsxs)("dl", { children: [
						/* @__PURE__ */ (0, C.jsxs)("div", { children: [/* @__PURE__ */ (0, C.jsx)("dt", { children: "下载尺寸" }), /* @__PURE__ */ (0, C.jsx)("dd", { children: t || `${s.width}×${s.height}px` })] }),
						/* @__PURE__ */ (0, C.jsxs)("div", { children: [/* @__PURE__ */ (0, C.jsx)("dt", { children: "循环方式" }), /* @__PURE__ */ (0, C.jsx)("dd", { children: s.kind === "panel" ? "定位区段循环" : "图案序列循环" })] }),
						/* @__PURE__ */ (0, C.jsxs)("div", { children: [/* @__PURE__ */ (0, C.jsx)("dt", { children: "检查引擎" }), /* @__PURE__ */ (0, C.jsx)("dd", { children: s.engine })] }),
						c && /* @__PURE__ */ (0, C.jsxs)("div", { children: [/* @__PURE__ */ (0, C.jsx)("dt", { children: "来源配置" }), /* @__PURE__ */ (0, C.jsxs)("dd", { children: [c.name, c.width && c.height ? ` · ${c.width}×${c.height}px` : ""] })] })
					] })
				]
			})
		]
	});
}
function Se({ src: e, alt: t, ...n }) {
	let [r, i] = (0, l.useState)(0), [a, o] = (0, l.useState)(!1), [s, c] = (0, l.useState)(!1);
	(0, l.useEffect)(() => {
		i(0), o(!1), c(!1);
	}, [e]);
	let u = r ? e + (e.includes("?") ? "&" : "?") + "retry=" + r : e, d = () => {
		o(!1), c(!1), i((e) => e + 1);
	};
	return /* @__PURE__ */ (0, C.jsxs)(C.Fragment, { children: [!a && /* @__PURE__ */ (0, C.jsx)("img", {
		...n,
		src: u,
		alt: t,
		onLoad: () => c(!0),
		onError: () => o(!0)
	}), a ? /* @__PURE__ */ (0, C.jsxs)("span", {
		className: "image-recovery",
		role: "status",
		children: [/* @__PURE__ */ (0, C.jsxs)("span", { children: [t || "图片", "加载失败"] }), /* @__PURE__ */ (0, C.jsx)("span", {
			role: "button",
			tabIndex: 0,
			className: "secondary small",
			onClick: (e) => {
				e.stopPropagation(), d();
			},
			onKeyDown: (e) => {
				(e.key === "Enter" || e.key === " ") && (e.preventDefault(), e.stopPropagation(), d());
			},
			children: "重新加载图片"
		})]
	}) : !s && n.loading !== "lazy" && /* @__PURE__ */ (0, C.jsx)("span", {
		className: "image-loading",
		children: "图片加载中…"
	})] });
}
var Ce = {
	queued: "等待处理",
	planning: "正在理解修改要求",
	rendering: "正在生成设计",
	editing: "正在编辑图像",
	saving: "正在保存结果",
	completed: "已保存",
	generating: "正在生成底图",
	validating: "正在检查结果",
	reconciling: "正在恢复任务",
	QUEUED: "等待处理",
	RUNNING: "正在处理",
	RECONCILING: "正在恢复任务",
	SUCCEEDED: "已保存",
	FAILED: "处理未完成"
};
function we({ active: e, view: t }) {
	let [n, r] = (0, l.useState)(null), [i, a] = (0, l.useState)(!0), [o, s] = (0, l.useState)("");
	return (0, l.useEffect)(() => {
		if (!e) return;
		let t = !1;
		return a(!0), g("/auth/me").then((e) => {
			t || r(e);
		}).catch((e) => {
			t || (r(null), s(de(e)));
		}).finally(() => {
			t || a(!1);
		}), () => {
			t = !0;
		};
	}, [e, t]), /* @__PURE__ */ (0, C.jsxs)(C.Fragment, { children: [
		i && /* @__PURE__ */ (0, C.jsxs)("div", {
			className: "page-loader",
			children: [/* @__PURE__ */ (0, C.jsx)("span", { className: "spinner" }), /* @__PURE__ */ (0, C.jsx)("span", { children: "正在连接丝带设计…" })]
		}),
		!i && !n && /* @__PURE__ */ (0, C.jsxs)("div", {
			className: "notice error",
			role: "alert",
			children: [
				/* @__PURE__ */ (0, C.jsx)("strong", { children: "丝带设计暂时无法打开" }),
				/* @__PURE__ */ (0, C.jsx)("p", { children: o || "登录已失效，请重新打开网站后继续。" }),
				/* @__PURE__ */ (0, C.jsx)("button", {
					type: "button",
					onClick: () => location.reload(),
					children: "重新载入"
				})
			]
		}),
		n && /* @__PURE__ */ (0, C.jsx)("div", {
			hidden: i,
			children: /* @__PURE__ */ (0, C.jsx)(j, {
				user: n,
				active: e && !i,
				view: t,
				onLogout: () => {
					r(null), s("登录已失效，请重新打开网站后继续。");
				}
			}, n.id)
		})
	] });
}
function j({ user: e, onLogout: t, active: n, view: r }) {
	let i = `ribbon:${e.id}:`, [a, o] = (0, l.useState)(0), [s, c] = (0, l.useState)(""), [u, _] = (0, l.useState)(!1), [v, te] = (0, l.useState)(""), ne = (0, l.useRef)(null), [w, re] = (0, l.useState)(null), [T, E] = (0, l.useState)([]), [D, ae] = (0, l.useState)([]), [oe, se] = (0, l.useState)([]), [k, we] = (0, l.useState)(null), [j, M] = (0, l.useState)(fe), [N, Te] = (0, l.useState)(null), [Ee, De] = (0, l.useState)("detail"), [Oe, ke] = (0, l.useState)(""), [Ae, je] = (0, l.useState)(""), [Me, Ne] = (0, l.useState)(null), [Pe, Fe] = (0, l.useState)(null), [Ie, Le] = (0, l.useState)(!0), [Re, ze] = (0, l.useState)(!1), [Be, Ve] = (0, l.useState)(!1), [He, Ue] = (0, l.useState)(null), [We, P] = (0, l.useState)(null), [Ge, Ke] = (0, l.useState)(() => x(i + "pending", null)), [qe, Je] = (0, l.useState)("layout"), [Ye, Xe] = (0, l.useState)("");
	(0, l.useEffect)(() => {
		We !== "pattern" && We !== "background" && Xe("");
	}, [We]);
	let [Ze, Qe] = (0, l.useState)(""), [$e, et] = (0, l.useState)(!1), [tt, nt] = (0, l.useState)(null), [rt, it] = (0, l.useState)(!1), [at, ot] = (0, l.useState)(null), [st, ct] = (0, l.useState)(0), [lt, ut] = (0, l.useState)(null), [dt, ft] = (0, l.useState)(null), [pt, mt] = (0, l.useState)([]), [ht, gt] = (0, l.useState)(!1), [_t, vt] = (0, l.useState)(!1), [yt, bt] = (0, l.useState)(null), [xt, St] = (0, l.useState)(null), Ct = (0, l.useRef)(null);
	(0, l.useEffect)(() => {
		n && r === "ribbon" || (ot(null), Ct.current = null);
	}, [n, r]);
	let wt = (0, l.useRef)(!1), Tt = (0, l.useRef)(null), Et = (0, l.useRef)(null), Dt = (0, l.useRef)(!1), Ot = (0, l.useRef)(null), kt = (0, l.useRef)(!0), At = (0, l.useRef)(null), jt = (0, l.useRef)(null), Mt = (0, l.useRef)(0), Nt = (0, l.useRef)(null), Pt = (0, l.useRef)(null);
	(0, l.useEffect)(() => (kt.current = !0, () => {
		kt.current = !1, Ot.current?.abort(), Nt.current?.abort(), Pt.current?.abort(), ne.current?.abort();
	}), []);
	let Ft = e.role === "admin", F = k?.versions?.find((e) => e.id === k.current_version_id), I = k?.versions?.find((e) => e.id === N) || F, It = Math.max(0, 2 - (k?.successful_refinement_count || 0)), Lt = !!k?.active_job_id || b(Me), L = b(Pe), R = Re || Lt || !!Ge || $e || !!lt, Rt = !!I && I.id !== k?.current_version_id, zt = I?.snapshot?.output_profile, Bt = [
		"seamless-unit-v1",
		"seamless-unit-v2",
		"seamless-unit-v3"
	].includes(I?.snapshot.loop?.engine || ""), Vt = !F || ["seamless-unit-v2", "seamless-unit-v3"].includes(F.snapshot.layout_engine || ""), Ht = !F || F.snapshot.layout_engine === "seamless-unit-v3", Ut = zt?.width && zt?.height && zt?.dpi ? `${zt.width}×${zt.height}px · ${zt.dpi} DPI · ${(zt.width / zt.dpi * 2.54).toFixed(1)}×${(zt.height / zt.dpi * 2.54).toFixed(1)} cm` : "", Wt = (0, l.useMemo)(() => new Map(T.map((e) => [e.id, e])), [T]), Gt = (0, l.useMemo)(() => {
		let e = {
			pattern: [],
			background: []
		};
		for (let t of T) e[t.kind].push({
			asset: t,
			query: t.name.toLocaleLowerCase()
		});
		return e;
	}, [T]), z = D.find((e) => e.id === j.template_id), Kt = Vt && ge[z?.mode || ""] || [], qt = Ht ? f[z?.mode || ""] : void 0, Jt = qt ? p(j.asset_ids, z?.mode || "", j.pattern_roles) : {}, Yt = ye(z?.mode, j.asset_ids.length, Vt) || (qt && j.asset_ids.length > 0 && !Object.values(Jt).includes("main") ? "至少保留一个主图，再安排配角、点缀或边饰。" : ""), Xt = j.asset_ids.length > 0 && !!j.background_id && !!z && !Yt, Zt = !!F && (JSON.stringify(F.snapshot.asset_refs) !== JSON.stringify(j.asset_ids) || F.snapshot.background_ref !== j.background_id || F.snapshot.template_id !== j.template_id || Ht && JSON.stringify(m(F.snapshot)) !== JSON.stringify(Jt) || (F.snapshot.border_ref || "") !== (j.border_ref || "") || Kt.some((e) => F.snapshot.zone_background_refs?.[e] !== j.zone_background_refs?.[e]) || (F.snapshot.background_tone || "original") !== (j.background_tone || "original") || (F.snapshot.design_density || "balanced") !== (j.design_density || "balanced")), Qt = j.asset_ids.map((e) => Wt.get(e)).filter(Boolean), $t = Wt.get(j.background_id), en = D.filter((e) => e.enabled || e.id === j.template_id), tn = en.filter((e) => pe.has(e.mode)), nn = en.filter((e) => !pe.has(e.mode)), rn = w?.provider === "test", an = rn ? w?.auth_mode !== "hsd" : w?.ai_ready === !0, on = w?.provider === "deepseek_seedream" && w?.ai_ready === !0 && w?.ai_draft_available === !0, sn = !F && !k?.versions?.length, cn = sn && on && yt !== !1, ln = cn && xt?.mode === z?.mode ? xt : null, un = Zt && (!Oe.trim() || ["应用所选配置", "应用新的素材与排版"].includes(Oe.trim())), dn = F?.editing || w?.editing, fn = Zt && dn && [
		"test",
		"openai",
		"deepseek_seedream"
	].includes(w?.provider || "") ? {
		...dn,
		allowed_operations: [
			"parameters",
			"edit_asset",
			"edit_background",
			...dn.composite_edit ? ["edit_composite"] : []
		],
		allowed_parameters: [
			"scale",
			"rotation",
			"offset_x",
			"offset_y",
			"background_color",
			...Vt || !["fullwidth", "ends_open"].includes(z?.mode || "") ? ["spacing"] : []
		]
	} : dn, pn = !un && (!an || fn?.allowed_operations.length === 0), mn = (e) => !fn || fn.allowed_operations.includes(e), hn = (Vt || z?.mode !== "fullwidth" && z?.mode !== "ends_open") && (!fn || fn.allowed_parameters.includes("spacing")), gn = qe === "layout" ? [
		...mn("parameters") ? [hn ? "图案缩小一些，间距拉开一点" : "图案缩小一些"] : [],
		...mn("edit_background") ? ["背景添加波点"] : [],
		...mn("edit_asset") ? ["给第一个图案添加星光"] : [],
		...mn("edit_composite") ? ["给画面添加星光"] : []
	] : qe.startsWith("zone:") || qe === "background" ? ["添加细小波点"] : qe === "border" ? ["保留边饰图案，添加细小星光"] : ["缩小一点", "向右移动10像素"];
	function _n(e) {
		return Vt && e.id === e.mode && e.version === 1 ? `/static/ribbon/${Ht ? "layout-v3" : "layout-v2"}/${e.mode}.webp` : e.thumbnail_url;
	}
	function vn(e) {
		return /* @__PURE__ */ (0, C.jsxs)("div", {
			className: "template-option",
			children: [/* @__PURE__ */ (0, C.jsxs)("button", {
				className: `template-card ${j.template_id === e.id ? "selected" : ""}`,
				disabled: R,
				"aria-pressed": j.template_id === e.id,
				onClick: () => yn({
					...j,
					template_id: e.id
				}),
				children: [/* @__PURE__ */ (0, C.jsx)(Se, {
					src: _n(e),
					alt: `${e.name}样式图`,
					loading: "lazy",
					decoding: "async"
				}), /* @__PURE__ */ (0, C.jsxs)("span", { children: [e.name, j.template_id === e.id && /* @__PURE__ */ (0, C.jsx)(O, {
					name: "check",
					size: 14
				})] })]
			}), /* @__PURE__ */ (0, C.jsx)("button", {
				type: "button",
				className: "template-example-button",
				"aria-label": `查看${e.name}案例`,
				onClick: () => {
					P(null), ot({
						mode: e.mode,
						name: e.name
					});
				},
				children: "查看案例"
			})]
		}, e.id);
	}
	function yn(e) {
		e.template_id !== j.template_id && (St(null), delete e.zone_background_refs, delete e.border_ref, delete e.pattern_roles);
		let t = D.find((t) => t.id === e.template_id)?.mode || "";
		Ht && f[t] ? e.pattern_roles = p(e.asset_ids, t, e.pattern_roles) : delete e.pattern_roles, qe !== "layout" && Je("layout"), M(e), S(i + "selection", {
			design_id: jt.current?.id || null,
			base_version_id: jt.current?.current_version_id || null,
			value: e
		});
	}
	function bn(e, t = !1) {
		let n = At.current !== e.current_version_id;
		if (jt.current = e, we(e), S(i + "design", e.id), se((t) => [e, ...t.filter((t) => t.id !== e.id)]), t || n) {
			Je("layout");
			let r = e.versions?.find((t) => t.id === e.current_version_id);
			De(r && ["ends", "ends_open"].includes(r.snapshot.template_mode) ? "fit" : "detail");
			let a = x(i + "selection", null), o = t && a?.design_id === e.id && a.base_version_id === e.current_version_id ? a.value : r ? {
				asset_ids: r.snapshot.asset_refs,
				background_id: r.snapshot.background_ref,
				template_id: r.snapshot.template_id,
				zone_background_refs: r.snapshot.zone_background_refs,
				border_ref: r.snapshot.border_ref,
				...r.snapshot.layout_engine === "seamless-unit-v3" ? { pattern_roles: m(r.snapshot) } : {},
				background_tone: r.snapshot.background_tone || "original",
				...[
					"design-rhythm-v1",
					"design-rhythm-v2",
					"seamless-unit-v1",
					"seamless-unit-v2",
					"seamless-unit-v3"
				].includes(r.snapshot.layout_engine || "") ? { design_density: r.snapshot.design_density || "balanced" } : {}
			} : fe;
			M(xe(o, r)), Te(e.current_version_id), At.current = e.current_version_id, n && ke("");
		}
		e.active_job && Ne(e.active_job);
	}
	async function xn() {
		let [e, t, n] = await Promise.all([
			g("/assets"),
			g("/templates"),
			g("/config")
		]);
		E(e), ae(t), re(n);
	}
	(0, l.useEffect)(() => {
		let e = !1, n = new AbortController();
		async function r() {
			Le(!0), c("");
			try {
				let t = await Promise.allSettled([
					g("/assets", { signal: n.signal }),
					g("/templates", { signal: n.signal }),
					g("/config", { signal: n.signal }),
					g("/designs?summary=true", { signal: n.signal })
				]);
				if (e) return;
				let [r, a, o, s] = t;
				r.status === "fulfilled" && E(r.value), a.status === "fulfilled" && ae(a.value), o.status === "fulfilled" && re(o.value), s.status === "fulfilled" && se(s.value);
				let c = t.find((e) => e.status === "rejected");
				if (c?.status === "rejected") throw c.reason;
				let l = r.status === "fulfilled" ? r.value : [], u = a.status === "fulfilled" ? a.value : [], d = s.status === "fulfilled" ? s.value : [], f = x(i + "design", null), p = d.find((e) => e.id === f)?.id || d[0]?.id;
				if (p) {
					let t = await g(`/designs/${p}`, { signal: n.signal });
					e || (bn(t, !0), t.active_job_id && Ue({
						text: "已恢复作品，正在同步后台任务。离开页面不会中断处理。",
						type: "info"
					}));
				} else {
					let e = x(i + "selection", null);
					M(xe(e?.value || be(l, u)));
				}
				let m = x(i + "backgroundJob", null);
				if (m) {
					let t = await g(`/jobs/${m}`, { signal: n.signal });
					e || Fe(t);
				}
			} catch (n) {
				e || (c(de(n)), n instanceof h && n.status === 401 && t());
			} finally {
				e || Le(!1);
			}
		}
		return r(), () => {
			e = !0, n.abort();
		};
	}, [a]), (0, l.useEffect)(() => {
		if (!n || !k?.id && !Pe?.id) return;
		let e = new AbortController(), r = Mt.current, a = k?.id, o = () => s || !kt.current || r !== Mt.current || a !== void 0 && jt.current?.id !== a, s = !1, c = !1, l = async () => {
			if (!(c || document.hidden)) {
				c = !0;
				try {
					if (Be && !k?.id && !b(Pe) && await g("/config", { signal: e.signal }), k?.id) {
						let t = await g(`/designs/${k.id}`, { signal: e.signal });
						if (o()) return;
						let n = jt.current;
						bn(t);
						let r = t.active_job_id || n?.active_job_id || Me?.id;
						if (r) {
							let t = await g(`/jobs/${r}`, { signal: e.signal });
							if (o()) return;
							Ne(t), t.status === "FAILED" && Me?.status !== "FAILED" && Ue({
								text: t.error || "此次处理未完成，已保留原结果，不扣精修次数。",
								type: "error"
							});
						}
					}
					if (Pe && b(Pe)) {
						let t = await g(`/jobs/${Pe.id}`, { signal: e.signal });
						if (o()) return;
						Fe(t), t.status === "FAILED" && (S(i + "backgroundJob", null), Ue({
							text: t.error || "底图未能生成，请重试。",
							type: "error"
						}));
					}
					Ve(!1);
				} catch (e) {
					o() || (Ve(!0), e instanceof h && e.status === 401 && t());
				} finally {
					c = !1;
				}
			}
		};
		Be || l();
		let u = Lt || L || Be ? window.setInterval(l, Be && !Lt && !L ? 2500 : 1200) : void 0;
		return document.addEventListener("visibilitychange", l), window.addEventListener("focus", l), () => {
			s = !0, e.abort(), clearInterval(u), document.removeEventListener("visibilitychange", l), window.removeEventListener("focus", l);
		};
	}, [
		n,
		Be,
		k?.id,
		k?.active_job_id,
		Pe?.id,
		Pe?.status,
		Me?.id,
		Me?.status
	]), (0, l.useEffect)(() => {
		let e = k?.versions.find((e) => e.id === k.current_version_id)?.snapshot;
		if (!e || Be || [
			...e.asset_refs,
			e.background_ref,
			...Object.values(e.zone_background_refs || {}),
			...e.border_ref ? [e.border_ref] : []
		].every((e) => T.some((t) => t.id === e))) return;
		let t = new AbortController(), n = Mt.current;
		return g("/assets", { signal: t.signal }).then((e) => {
			!t.signal.aborted && kt.current && n === Mt.current && E(e);
		}).catch(() => {
			!t.signal.aborted && n === Mt.current && Ve(!0);
		}), () => t.abort();
	}, [k?.current_version_id, Be]), (0, l.useEffect)(() => {
		if (Pe?.status !== "SUCCEEDED" || !Pe.result_asset_id || x(i + "backgroundJob", null) !== Pe.id || Be) return;
		let e = new AbortController();
		return g("/assets", { signal: e.signal }).then((t) => {
			if (e.signal.aborted || !kt.current) return;
			E(t);
			let n = x(i + "backgroundTarget", null);
			n && n.design_id !== (jt.current?.id || null) || M((e) => {
				let t = {
					...e,
					background_id: Pe.result_asset_id
				};
				return S(i + "selection", {
					design_id: jt.current?.id || null,
					base_version_id: jt.current?.current_version_id || null,
					value: t
				}), t;
			}), S(i + "backgroundJob", null), Ue({
				text: "已恢复上次完成的底图。",
				type: "success"
			});
		}).catch(() => {
			!e.signal.aborted && kt.current && Ve(!0);
		}), () => e.abort();
	}, [
		Pe?.id,
		Pe?.status,
		Be
	]);
	async function Sn(e) {
		Ke(e), S(i + "pending", e);
		try {
			let t = await y(e.path, e.body);
			if (Ke(null), S(i + "pending", null), Ue(null), e.kind === "background") S(i + "backgroundTarget", { design_id: e.designId || null }), Fe(t), S(i + "backgroundJob", t.id);
			else if (Ne(t), e.designId) try {
				bn(await g(`/designs/${e.designId}`));
			} catch {
				Ve(!0), Ue({
					text: "任务已接受，正在等待连接恢复以同步结果。",
					type: "info"
				});
			}
		} catch (e) {
			e instanceof h && e.status >= 400 && e.status < 500 && e.status !== 408 && (Ke(null), S(i + "pending", null)), Ue({
				text: e instanceof h && e.status >= 400 && e.status < 500 && e.status !== 408 ? de(e) : "连接中断，提交结果尚未确认。请点击“恢复提交”，将使用原请求安全查询或继续。",
				type: "error"
			});
		}
	}
	async function Cn(e) {
		if (!wt.current) {
			wt.current = !0, ze(!0);
			try {
				await e();
			} catch (e) {
				Ue({
					text: de(e),
					type: "error"
				});
			} finally {
				wt.current = !1, ze(!1);
			}
		}
	}
	async function wn() {
		!R && Xt && await Cn(async () => {
			let e = k;
			e || (e = await y("/designs", { name: `丝带设计 ${(/* @__PURE__ */ new Date()).toLocaleDateString("zh-CN")}` }), bn(e)), await Sn({
				path: `/designs/${e.id}/generate`,
				body: {
					idempotency_key: crypto.randomUUID(),
					...j,
					pattern_roles: qt ? Jt : void 0,
					ai_assisted: cn,
					reference_code: ln?.code || null
				},
				kind: "design",
				designId: e.id
			});
		});
	}
	async function Tn() {
		R || !F || It === 0 || Rt || !Xt || pn || !Oe.trim() && !Zt || await Cn(() => Sn({
			path: `/designs/${k.id}/refinements`,
			body: {
				idempotency_key: crypto.randomUUID(),
				base_version_id: F.id,
				...Vt && qe !== "layout" ? { edit_target: qe } : {},
				prompt: Oe.trim() || (Zt ? "应用所选配置" : ""),
				...Zt ? { selection: {
					...j,
					pattern_roles: qt ? Jt : void 0
				} } : {}
			},
			kind: "design",
			designId: k.id
		}));
	}
	async function En() {
		!R && F?.parent_version_id && await Cn(async () => {
			bn(await y(`/designs/${k.id}/rollback`, { expected_version_id: F.id })), Ne(null), Ue({
				text: "已回退到当前版本的父版本。累计精修次数保持不变。",
				type: "success"
			});
		});
	}
	async function Dn() {
		Re || Ge || L || $e || (++Mt.current, Nt.current?.abort(), ut(null), bt(null), St(null), await Cn(async () => {
			let e = await y("/designs", { name: `丝带设计 ${oe.length + 1}` });
			At.current = null, bn(e, !0), yn(be(T, D)), ke(""), Ne(null), Ue(null), P(null);
		}));
	}
	async function On(e) {
		if (Re || Ge || L || $e) return;
		let n = ++Mt.current;
		Nt.current?.abort();
		let r = new AbortController();
		Nt.current = r;
		let i = oe.find((t) => t.id === e)?.name || "所选作品";
		ut({
			id: e,
			name: i,
			loading: !0
		}), jt.current = null, we(null), Te(null), M(fe), At.current = null, Ne(null), ke(""), bt(null), St(null), Ue(null), P(null);
		try {
			let t = await g(`/designs/${e}`, { signal: r.signal });
			if (!kt.current || n !== Mt.current || r.signal.aborted) return;
			bn(t, !0), ut(null), Ne(t.active_job || null), Ve(!1);
		} catch (a) {
			if (!kt.current || n !== Mt.current || r.signal.aborted) return;
			ut({
				id: e,
				name: i,
				loading: !1
			}), Ue({
				text: de(a),
				type: "error"
			}), a instanceof h && a.status === 401 && t();
		}
	}
	async function kn() {
		P("designs"), gt(!1), ft(null), te(""), ne.current?.abort();
		let e = new AbortController();
		ne.current = e, _(!0);
		try {
			let t = await g("/designs?summary=true", { signal: e.signal });
			!e.signal.aborted && kt.current && se(t);
		} catch (t) {
			!e.signal.aborted && kt.current && te(de(t));
		} finally {
			!e.signal.aborted && kt.current && _(!1);
		}
	}
	async function An() {
		Pt.current?.abort();
		let e = new AbortController();
		Pt.current = e, vt(!0);
		try {
			let t = await g("/designs?deleted=true&summary=true", { signal: e.signal });
			!e.signal.aborted && kt.current && mt(t);
		} catch (t) {
			!e.signal.aborted && kt.current && Ue({
				text: de(t),
				type: "error"
			});
		} finally {
			!e.signal.aborted && kt.current && vt(!1);
		}
	}
	async function jn(e) {
		Re || Ge || $e || L || lt?.loading || e.active_job_id || await Cn(async () => {
			await g(`/designs/${e.id}`, { method: "DELETE" }), kt.current && (Pt.current?.abort(), vt(!1), se((t) => t.filter((t) => t.id !== e.id)), mt((t) => [e, ...t.filter((t) => t.id !== e.id)]), (jt.current?.id === e.id || lt?.id === e.id) && (++Mt.current, Nt.current?.abort(), jt.current = null, we(null), ut(null), Te(null), At.current = null, Ne(null), ke(""), bt(null), St(null), M(be(T, D)), S(i + "design", null), S(i + "selection", null)), ft(null), Ue({
				text: `作品已删除，可在“已删除作品”中恢复；保留 ${w?.retention_hours ?? 50} 小时，累计精修次数不变。`,
				type: "success"
			}));
		});
	}
	async function Mn(e) {
		Pt.current?.abort(), vt(!1), await Cn(async () => {
			let t = await y(`/designs/${e.id}/restore`, {});
			kt.current && (se((n) => [t, ...n.filter((t) => t.id !== e.id)]), mt((t) => t.filter((t) => t.id !== e.id)), Ue({
				text: "作品已恢复，版本与累计精修次数保持不变。",
				type: "success"
			}));
		});
	}
	async function Nn() {
		R || L || (an ? await Cn(() => Sn({
			path: "/background-jobs",
			body: {
				idempotency_key: crypto.randomUUID(),
				prompt: Ae.trim()
			},
			kind: "background",
			designId: k?.id
		})) : Ue({
			text: "AI 服务尚未配置，请联系管理员；仍可使用已有底图生成首稿。",
			type: "info"
		}));
	}
	async function Pn(e, n) {
		if (!e?.length || Dt.current || R) return;
		let r = Array.from(e), a = Ft && rt;
		Dt.current = !0;
		let o = new AbortController();
		Ot.current = o, et(!0), nt({
			completed: 0,
			total: r.length
		}), Ue({
			text: `正在上传第 1 / ${r.length} 张…`,
			type: "info"
		});
		let s = [];
		try {
			for (let [e, t] of r.entries()) {
				if (!kt.current) return;
				let c = new FormData();
				c.append("file", t), c.append("kind", n), c.append("name", t.name.replace(/\.[^.]+$/, "")), c.append("shared", String(a));
				let l = await g("/assets", {
					method: "POST",
					body: c,
					signal: o.signal
				});
				if (!kt.current) return;
				s.push(l), E((e) => e.some((e) => e.id === l.id) ? e.map((e) => e.id === l.id ? l : e) : [...e, l]), M((e) => {
					let t = n === "pattern" ? {
						...e,
						asset_ids: [.../* @__PURE__ */ new Set([...e.asset_ids, l.id])].slice(0, 12)
					} : {
						...e,
						background_id: l.id
					};
					return S(i + "selection", {
						design_id: jt.current?.id || null,
						base_version_id: jt.current?.current_version_id || null,
						value: t
					}), t;
				}), nt({
					completed: s.length,
					total: r.length
				}), e + 1 < r.length && Ue({
					text: `已上传 ${s.length} / ${r.length} 张，正在上传第 ${e + 2} 张…`,
					type: "info"
				});
			}
			Ue({
				text: `已上传 ${s.length} 个${n === "pattern" ? "图案" : "底图"}。`,
				type: "success"
			});
		} catch (e) {
			if (!kt.current) return;
			e instanceof h && e.status === 401 && t();
			let n = e instanceof h ? de(e) : "本张上传结果尚未确认。请重新载入网页，在素材库查看后再决定是否重传。";
			Ue({
				text: s.length ? `已上传 ${s.length} 个，其余未完成：${n}` : n,
				type: "error"
			});
		} finally {
			Dt.current = !1, Ot.current = null, kt.current && (et(!1), nt(null)), Tt.current && (Tt.current.value = ""), Et.current && (Et.current.value = "");
		}
	}
	function Fn(e) {
		R || (!j.asset_ids.includes(e) && j.asset_ids.length >= 12 ? Ue({
			text: "每份设计最多选择 12 个图案。",
			type: "info"
		}) : yn({
			...j,
			asset_ids: j.asset_ids.includes(e) ? j.asset_ids.filter((t) => t !== e) : [...j.asset_ids, e]
		}));
	}
	(0, l.useEffect)(() => {
		n ? r === "ribbon-admin" && (Ft ? P("admin") : Ue({
			text: "排版与规格维护仅供管理员使用。",
			type: "error"
		})) : P(null);
	}, [
		n,
		r,
		Ft
	]);
	async function In(e) {
		await Cn(async () => {
			await g(`/assets/${e.id}`, { method: "DELETE" }), E((t) => t.filter((t) => t.id !== e.id)), yn({
				...j,
				asset_ids: j.asset_ids.filter((t) => t !== e.id),
				background_id: j.background_id === e.id ? "" : j.background_id,
				border_ref: j.border_ref === e.id ? void 0 : j.border_ref,
				zone_background_refs: j.zone_background_refs && Object.fromEntries(Object.entries(j.zone_background_refs).filter(([, t]) => t !== e.id))
			});
		});
	}
	let Ln = lt ? lt.loading ? "正在打开作品" : "作品打开失败" : Lt ? Ce[Me?.phase || ""] || Me?.phase || Ce[Me?.status || ""] || "正在处理" : F ? It ? "可继续精修" : "精修已用完" : Xt ? "可以生成首稿" : "等待选择素材", Rn = (0, l.useMemo)(() => {
		if (We !== "pattern" && We !== "background") return [];
		let e = Ze.toLocaleLowerCase().trim();
		return e ? Gt[We].filter((t) => t.query.includes(e)).map((e) => e.asset) : Gt[We].map((e) => e.asset);
	}, [
		Gt,
		We,
		Ze
	]), zn = Math.max(1, Math.ceil(Rn.length / 36)), Bn = Math.min(st, zn - 1), Vn = Rn.slice(Bn * 36, (Bn + 1) * 36);
	return (0, l.useEffect)(() => {
		ct(0);
	}, [We, Ze]), /* @__PURE__ */ (0, C.jsxs)("div", {
		className: "app-shell",
		children: [
			/* @__PURE__ */ (0, C.jsxs)("header", {
				className: "topbar",
				children: [/* @__PURE__ */ (0, C.jsx)(ue, {}), /* @__PURE__ */ (0, C.jsxs)("div", {
					className: "header-actions",
					children: [
						/* @__PURE__ */ (0, C.jsxs)("button", {
							className: "secondary",
							disabled: Re || !!Ge || L || $e,
							onClick: () => void Dn(),
							children: [/* @__PURE__ */ (0, C.jsx)(O, { name: "plus" }), "新建作品"]
						}),
						/* @__PURE__ */ (0, C.jsxs)("button", {
							className: "text-button",
							onClick: () => void kn(),
							children: [
								/* @__PURE__ */ (0, C.jsx)(O, { name: "folder" }),
								"我的作品",
								/* @__PURE__ */ (0, C.jsx)("span", {
									className: "count",
									children: oe.length
								})
							]
						}),
						Ft && /* @__PURE__ */ (0, C.jsxs)("button", {
							className: "text-button",
							onClick: () => P("admin"),
							children: [/* @__PURE__ */ (0, C.jsx)(O, { name: "settings" }), "排版与规格"]
						})
					]
				})]
			}),
			/* @__PURE__ */ (0, C.jsxs)("main", { children: [
				w && (rn || !an || w.output_profile?.is_demo) && /* @__PURE__ */ (0, C.jsxs)("div", {
					className: "environment-strip compact-status",
					children: [
						rn && /* @__PURE__ */ (0, C.jsx)("span", {
							className: F ? void 0 : "test-limit",
							children: "测试模型 · 演示模式（测试替身）"
						}),
						w.output_profile?.is_demo && /* @__PURE__ */ (0, C.jsx)("span", { children: "演示输出 · 未经业务验收" }),
						!an && /* @__PURE__ */ (0, C.jsx)("span", { children: "AI 尚未配置，可用已有素材排版。" })
					]
				}),
				He && /* @__PURE__ */ (0, C.jsxs)("div", {
					className: `notice ${He.type}`,
					role: He.type === "error" ? "alert" : "status",
					children: [/* @__PURE__ */ (0, C.jsx)("span", { children: He.text }), /* @__PURE__ */ (0, C.jsx)("button", {
						"aria-label": "关闭提示",
						className: "icon-button",
						onClick: () => Ue(null),
						children: /* @__PURE__ */ (0, C.jsx)(O, {
							name: "close",
							size: 15
						})
					})]
				}),
				Be && /* @__PURE__ */ (0, C.jsx)("div", {
					className: "notice error",
					role: "status",
					children: "连接暂时中断，正在重连。后台任务和已保存版本不会因此重置。"
				}),
				Ge && /* @__PURE__ */ (0, C.jsxs)("div", {
					className: "notice info",
					children: [/* @__PURE__ */ (0, C.jsx)("span", { children: "有一项提交尚未确认；恢复使用原幂等键，不会重复扣次。" }), /* @__PURE__ */ (0, C.jsx)("button", {
						className: "secondary small",
						disabled: Re,
						onClick: () => void Cn(() => Sn(Ge)),
						children: "恢复提交"
					})]
				}),
				s && /* @__PURE__ */ (0, C.jsxs)("div", {
					className: "notice error",
					role: "alert",
					children: [/* @__PURE__ */ (0, C.jsxs)("span", { children: ["工作台读取未完成：", s] }), /* @__PURE__ */ (0, C.jsx)("button", {
						className: "secondary small",
						onClick: () => o((e) => e + 1),
						children: "重新读取工作台"
					})]
				}),
				Ie ? /* @__PURE__ */ (0, C.jsxs)("div", {
					className: "page-loader in-page",
					children: [/* @__PURE__ */ (0, C.jsx)("span", { className: "spinner" }), "正在恢复作品和素材…"]
				}) : /* @__PURE__ */ (0, C.jsxs)("div", {
					className: `workspace-grid ${F ? "" : "draft-workspace"}`,
					children: [
						/* @__PURE__ */ (0, C.jsxs)("aside", {
							className: "panel source-panel",
							children: [
								/* @__PURE__ */ (0, C.jsxs)("div", {
									className: "panel-heading",
									children: [/* @__PURE__ */ (0, C.jsx)("div", { children: /* @__PURE__ */ (0, C.jsx)("h2", { children: "素材与排版" }) }), /* @__PURE__ */ (0, C.jsx)(O, { name: "grid" })]
								}),
								/* @__PURE__ */ (0, C.jsxs)("section", {
									className: "source-section",
									children: [
										/* @__PURE__ */ (0, C.jsxs)("div", {
											className: "section-label",
											children: [/* @__PURE__ */ (0, C.jsx)("h3", { children: "图案" }), /* @__PURE__ */ (0, C.jsxs)("span", { children: [
												"已选 ",
												j.asset_ids.length,
												" 个"
											] })]
										}),
										/* @__PURE__ */ (0, C.jsxs)("div", {
											className: "two-actions",
											children: [/* @__PURE__ */ (0, C.jsxs)("button", {
												className: "secondary",
												disabled: R || $e,
												onClick: () => {
													it(!1), Tt.current?.click();
												},
												children: [/* @__PURE__ */ (0, C.jsx)(O, {
													name: "upload",
													size: 16
												}), $e ? `上传 ${tt?.completed || 0}/${tt?.total || 0}` : "上传图案"]
											}), /* @__PURE__ */ (0, C.jsxs)("button", {
												className: "secondary",
												disabled: R,
												onClick: () => {
													Qe(""), P("pattern");
												},
												children: [/* @__PURE__ */ (0, C.jsx)(O, {
													name: "folder",
													size: 16
												}), "素材库"]
											})]
										}),
										/* @__PURE__ */ (0, C.jsx)("input", {
											ref: Tt,
											type: "file",
											accept: "image/png,image/jpeg,image/webp",
											multiple: !0,
											hidden: !0,
											onChange: (e) => void Pn(e.target.files, "pattern")
										}),
										Qt.length ? /* @__PURE__ */ (0, C.jsx)("div", {
											className: `selected-patterns${qt ? " has-pattern-roles" : ""}`,
											children: Qt.map((e, t) => /* @__PURE__ */ (0, C.jsxs)("div", {
												className: "pattern-tile",
												children: [
													/* @__PURE__ */ (0, C.jsxs)("div", {
														className: "checker",
														children: [/* @__PURE__ */ (0, C.jsx)(Se, {
															src: e.thumbnail_url || e.url,
															alt: e.name,
															decoding: "async"
														}), /* @__PURE__ */ (0, C.jsx)("button", {
															className: "remove-asset",
															disabled: R,
															"aria-label": `移除${e.name}`,
															onClick: () => Fn(e.id),
															children: "×"
														})]
													}),
													/* @__PURE__ */ (0, C.jsxs)("span", {
														title: `第 ${t + 1} 个图案：${e.name}`,
														children: [
															t + 1,
															". ",
															e.name
														]
													}),
													qt && /* @__PURE__ */ (0, C.jsx)("select", {
														className: "pattern-role",
														"aria-label": `图案 ${t + 1} 的排版角色`,
														value: Jt[e.id],
														disabled: R,
														onChange: (t) => yn({
															...j,
															pattern_roles: {
																...Jt,
																[e.id]: t.target.value
															}
														}),
														children: qt.map((e) => /* @__PURE__ */ (0, C.jsx)("option", {
															value: e.value,
															children: e.label
														}, e.value))
													})
												]
											}, e.id))
										}) : /* @__PURE__ */ (0, C.jsxs)("button", {
											className: "empty-patterns",
											disabled: R,
											onClick: () => {
												Qe(""), P("pattern");
											},
											children: [
												/* @__PURE__ */ (0, C.jsx)(O, { name: "plus" }),
												/* @__PURE__ */ (0, C.jsx)("span", { children: "从素材库开始，或上传已有图案" }),
												/* @__PURE__ */ (0, C.jsx)("small", { children: "支持多个透明 PNG 图案" })
											]
										})
									]
								}),
								/* @__PURE__ */ (0, C.jsxs)("section", {
									className: "source-section",
									children: [
										/* @__PURE__ */ (0, C.jsxs)("div", {
											className: "section-label",
											children: [/* @__PURE__ */ (0, C.jsx)("h3", { children: "排版模式" }), /* @__PURE__ */ (0, C.jsx)("button", {
												type: "button",
												className: "template-examples-all",
												onClick: () => ot({
													mode: null,
													name: "全部排版案例"
												}),
												children: "查看全部案例"
											})]
										}),
										/* @__PURE__ */ (0, C.jsx)("div", {
											className: "template-grid",
											children: tn.map(vn)
										}),
										nn.length > 0 && /* @__PURE__ */ (0, C.jsx)("div", {
											className: "more-layouts",
											children: /* @__PURE__ */ (0, C.jsxs)("button", {
												type: "button",
												className: "more-layouts-toggle",
												"aria-expanded": We === "layouts",
												"aria-haspopup": "dialog",
												onClick: () => P("layouts"),
												children: [/* @__PURE__ */ (0, C.jsxs)("span", { children: [
													"更多排法（",
													nn.length,
													"）"
												] }), /* @__PURE__ */ (0, C.jsx)("span", {
													"aria-hidden": "true",
													children: "›"
												})]
											})
										}),
										z && !pe.has(z.mode) && /* @__PURE__ */ (0, C.jsxs)("div", {
											className: "chosen-layout",
											children: [/* @__PURE__ */ (0, C.jsxs)("strong", { children: ["已选：", z.name] }), /* @__PURE__ */ (0, C.jsxs)("button", {
												type: "button",
												className: "template-example-button",
												onClick: () => ot({
													mode: z.mode,
													name: z.name
												}),
												children: [
													"查看",
													z.name,
													"案例"
												]
											})]
										}),
										z && (Vt && ve[z.mode] || me[z.mode]) && /* @__PURE__ */ (0, C.jsx)("p", {
											className: "layout-selection-help",
											children: Ht && _e[z.mode] || Vt && ve[z.mode] || me[z.mode]
										}),
										Yt && /* @__PURE__ */ (0, C.jsx)("p", {
											className: "layout-selection-issue",
											id: "ribbon-layout-issue",
											role: "alert",
											children: Yt
										}),
										(!F || [
											"design-rhythm-v1",
											"design-rhythm-v2",
											"seamless-unit-v1",
											"seamless-unit-v2",
											"seamless-unit-v3"
										].includes(F.snapshot.layout_engine || "")) && /* @__PURE__ */ (0, C.jsxs)("label", {
											className: "density-control",
											children: ["画面密度", /* @__PURE__ */ (0, C.jsxs)("select", {
												"aria-label": "画面密度",
												value: j.design_density || "balanced",
												disabled: R,
												onChange: (e) => yn({
													...j,
													design_density: e.target.value
												}),
												children: [
													/* @__PURE__ */ (0, C.jsx)("option", {
														value: "airy",
														children: "疏朗"
													}),
													/* @__PURE__ */ (0, C.jsx)("option", {
														value: "balanced",
														children: "均衡"
													}),
													/* @__PURE__ */ (0, C.jsx)("option", {
														value: "rich",
														children: "饱满"
													})
												]
											})]
										})
									]
								}),
								Vt && (Kt.length > 0 || z?.mode === "bordered") && /* @__PURE__ */ (0, C.jsxs)("details", {
									className: "optional-layers",
									children: [/* @__PURE__ */ (0, C.jsx)("summary", { children: Kt.length ? "分区底纹" : "独立边饰" }), (Kt.length ? Kt : ["border"]).map((e) => {
										let t = e === "border" ? j.border_ref : j.zone_background_refs?.[e];
										return /* @__PURE__ */ (0, C.jsxs)("div", { children: [
											/* @__PURE__ */ (0, C.jsx)("span", { children: he[e] || "上下边饰" }),
											/* @__PURE__ */ (0, C.jsx)("button", {
												"aria-label": e === "border" ? "选择上下边饰" : `选择${he[e]}底纹`,
												disabled: R,
												className: "secondary small",
												onClick: () => {
													Xe(e), Qe(""), P(e === "border" ? "pattern" : "background");
												},
												children: t && Wt.get(t)?.name || (e === "border" ? "选择边饰" : "选择底纹")
											}),
											t && /* @__PURE__ */ (0, C.jsx)("button", {
												disabled: R,
												className: "text-button",
												onClick: () => {
													let t = {
														...j,
														zone_background_refs: { ...j.zone_background_refs }
													};
													e === "border" ? delete t.border_ref : delete t.zone_background_refs[e], yn(t);
												},
												children: "恢复默认"
											})
										] }, e);
									})]
								}, z?.mode),
								/* @__PURE__ */ (0, C.jsxs)("section", {
									className: "source-section background-section",
									children: [
										/* @__PURE__ */ (0, C.jsxs)("div", {
											className: "section-label",
											children: [/* @__PURE__ */ (0, C.jsx)("h3", { children: "底图" }), $t?.is_demo && /* @__PURE__ */ (0, C.jsx)("span", {
												className: "tiny-pill",
												children: "演示素材"
											})]
										}),
										/* @__PURE__ */ (0, C.jsxs)("div", {
											className: "two-actions",
											children: [/* @__PURE__ */ (0, C.jsxs)("button", {
												className: "secondary",
												disabled: R,
												onClick: () => {
													Qe(""), P("background");
												},
												children: [/* @__PURE__ */ (0, C.jsx)(O, {
													name: "folder",
													size: 16
												}), "底图库"]
											}), /* @__PURE__ */ (0, C.jsxs)("button", {
												className: "secondary",
												disabled: R || L || !an,
												onClick: () => void Nn(),
												children: [L ? /* @__PURE__ */ (0, C.jsx)("span", { className: "spinner tiny" }) : /* @__PURE__ */ (0, C.jsx)(O, {
													name: "spark",
													size: 16
												}), rn ? "生成测试底图" : "AI 生成底图"]
											})]
										}),
										/* @__PURE__ */ (0, C.jsx)("label", {
											className: "background-prompt-label",
											htmlFor: "background-prompt",
											children: "底图要求（可不填）"
										}),
										/* @__PURE__ */ (0, C.jsx)("textarea", {
											id: "background-prompt",
											className: "background-prompt",
											value: Ae,
											onChange: (e) => je(e.target.value),
											maxLength: 2e3,
											rows: 2,
											disabled: R || L || !an,
											placeholder: "例如：浅蓝色细条纹，不要文字；不填则随机生成。",
											"aria-describedby": an ? void 0 : "background-ai-unavailable"
										}),
										!an && /* @__PURE__ */ (0, C.jsx)("p", {
											className: "model-help",
											id: "background-ai-unavailable",
											children: "AI 尚未配置，仍可从底图库选图或上传后生成首稿。"
										}),
										$t ? /* @__PURE__ */ (0, C.jsxs)("div", {
											className: "background-selected",
											children: [
												/* @__PURE__ */ (0, C.jsx)(Se, {
													src: $t.thumbnail_url || $t.url,
													alt: "选中的底图",
													loading: "lazy",
													decoding: "async"
												}),
												/* @__PURE__ */ (0, C.jsxs)("div", { children: [/* @__PURE__ */ (0, C.jsx)("strong", { children: $t.name }), /* @__PURE__ */ (0, C.jsx)("small", { children: $t.source === "upload" ? "已上传" : "已选择" })] }),
												/* @__PURE__ */ (0, C.jsx)(O, {
													name: "check",
													size: 16
												})
											]
										}) : /* @__PURE__ */ (0, C.jsx)("div", {
											className: "empty-background",
											children: "选择底图，为图案定下基调"
										}),
										L && /* @__PURE__ */ (0, C.jsxs)("p", {
											className: "microcopy",
											children: [
												rn ? "正在生成测试底图…" : "AI 正在生成底图…",
												" ",
												"可离开后恢复。"
											]
										}),
										/* @__PURE__ */ (0, C.jsxs)("label", {
											className: "background-tone-control",
											children: [/* @__PURE__ */ (0, C.jsx)("input", {
												type: "checkbox",
												checked: j.background_tone === "soft",
												disabled: R || L,
												onChange: (e) => yn({
													...j,
													background_tone: e.target.checked ? "soft" : "original"
												})
											}), "柔和底纹，突出主图"]
										})
									]
								}),
								F && Zt && /* @__PURE__ */ (0, C.jsx)("div", {
									className: "selection-warning",
									children: "素材或排版已更改。点击右侧“开始精修”应用，会计入本作品精修次数。"
								})
							]
						}),
						/* @__PURE__ */ (0, C.jsxs)("section", {
							className: "center-column",
							children: [/* @__PURE__ */ (0, C.jsxs)("div", {
								className: "panel preview-panel",
								children: [
									/* @__PURE__ */ (0, C.jsxs)("div", {
										className: "panel-heading",
										children: [/* @__PURE__ */ (0, C.jsx)("div", { children: /* @__PURE__ */ (0, C.jsx)("h2", { children: lt?.name || k?.name || "设计预览" }) }), /* @__PURE__ */ (0, C.jsxs)("span", {
											className: `state-pill ${Lt ? "working" : ""}`,
											children: [/* @__PURE__ */ (0, C.jsx)("span", { className: "status-dot" }), Ln]
										})]
									}),
									I ? /* @__PURE__ */ (0, C.jsxs)("div", {
										className: "result-actions",
										children: [/* @__PURE__ */ (0, C.jsxs)("button", {
											className: "secondary",
											disabled: R || !F?.parent_version_id,
											onClick: () => void En(),
											children: [/* @__PURE__ */ (0, C.jsx)(O, {
												name: "back",
												size: 17
											}), "回退上一版"]
										}), /* @__PURE__ */ (0, C.jsxs)("a", {
											className: "primary",
											href: I.download_url,
											download: !0,
											children: [/* @__PURE__ */ (0, C.jsx)(O, {
												name: "download",
												size: 17
											}), Rt ? "下载所选版本" : Bt ? "下载循环单元" : "下载当前图"]
										})]
									}) : /* @__PURE__ */ (0, C.jsxs)("div", {
										className: "generate-area",
										children: [
											/* @__PURE__ */ (0, C.jsxs)("button", {
												className: "primary full",
												disabled: !Xt || R || L,
												"aria-describedby": Yt ? "ribbon-layout-issue" : void 0,
												onClick: () => void wn(),
												children: [
													Lt ? /* @__PURE__ */ (0, C.jsx)("span", { className: "spinner tiny" }) : /* @__PURE__ */ (0, C.jsx)(O, { name: "spark" }),
													Re && Ge ? "正在提交…" : Lt ? "正在生成首稿…" : "生成首稿",
													/* @__PURE__ */ (0, C.jsx)(O, {
														name: "arrow",
														size: 16
													})
												]
											}),
											sn && !lt && on && /* @__PURE__ */ (0, C.jsxs)("div", {
												className: "ai-draft-options",
												children: [/* @__PURE__ */ (0, C.jsxs)("label", { children: [/* @__PURE__ */ (0, C.jsx)("input", {
													type: "checkbox",
													checked: cn,
													disabled: R || L,
													onChange: (e) => {
														bt(e.target.checked), e.target.checked || St(null);
													}
												}), "AI搭配底纹与装饰"] }), cn ? /* @__PURE__ */ (0, C.jsxs)(C.Fragment, { children: [/* @__PURE__ */ (0, C.jsx)("p", { children: "按原图保留人物文字。选择的案例会发送给Seedream。" }), ln ? /* @__PURE__ */ (0, C.jsxs)("div", {
													className: "ai-draft-reference",
													children: [/* @__PURE__ */ (0, C.jsxs)("span", { children: ["参考案例：", /* @__PURE__ */ (0, C.jsx)("strong", { children: ln.code })] }), /* @__PURE__ */ (0, C.jsx)("button", {
														type: "button",
														disabled: R,
														onClick: () => St(null),
														children: "取消案例参考"
													})]
												}) : /* @__PURE__ */ (0, C.jsx)("button", {
													type: "button",
													className: "ai-reference-picker",
													disabled: R || !z,
													onClick: () => ot({
														mode: z?.mode || null,
														name: z?.name || "全部排版案例"
													}),
													children: "选择案例参考"
												})] }) : /* @__PURE__ */ (0, C.jsx)("p", { children: "按原素材直接排版，首稿不调用AI搭配。" })]
											}),
											/* @__PURE__ */ (0, C.jsx)("small", { children: j.asset_ids.length ? j.template_id ? j.background_id ? Yt || "首稿不占用精修次数" : "请选择或生成底图" : "请选择一种排版模式" : "请先选择至少一个图案" })
										]
									}),
									/* @__PURE__ */ (0, C.jsxs)("div", {
										className: `preview-stage ${I ? "is-filled" : "is-empty"}`,
										children: [
											/* @__PURE__ */ (0, C.jsxs)("div", {
												className: "stage-topline",
												children: [/* @__PURE__ */ (0, C.jsx)("span", { children: I ? `V${I.sequence} · ${ee(I)}` : "你的设计画布" }), I && /* @__PURE__ */ (0, C.jsx)("span", { children: I.id === k?.current_version_id ? "当前版本" : "历史版本" })]
											}),
											lt ? /* @__PURE__ */ (0, C.jsx)("div", {
												className: "empty-canvas design-loading",
												role: "status",
												"aria-live": "polite",
												children: lt.loading ? /* @__PURE__ */ (0, C.jsxs)(C.Fragment, { children: [
													/* @__PURE__ */ (0, C.jsx)("span", { className: "spinner" }),
													/* @__PURE__ */ (0, C.jsx)("h3", { children: "正在打开作品…" }),
													/* @__PURE__ */ (0, C.jsx)("p", { children: "正在读取所选作品的版本和素材。" })
												] }) : /* @__PURE__ */ (0, C.jsxs)(C.Fragment, { children: [
													/* @__PURE__ */ (0, C.jsx)("h3", { children: "作品打开失败" }),
													/* @__PURE__ */ (0, C.jsx)("p", { children: "请重试，或从“我的作品”选择其他作品。" }),
													/* @__PURE__ */ (0, C.jsx)("button", {
														className: "secondary",
														onClick: () => void On(lt.id),
														children: "重试打开作品"
													})
												] })
											}) : I && Bt ? /* @__PURE__ */ (0, C.jsx)(A, {
												version: I,
												sizeLabel: Ut,
												target: Rt ? "layout" : qe
											}, `${k?.id}:${I.id}`) : I ? /* @__PURE__ */ (0, C.jsxs)(C.Fragment, { children: [/* @__PURE__ */ (0, C.jsx)("div", {
												className: `ribbon-display ${Ee}`,
												children: /* @__PURE__ */ (0, C.jsx)(Se, {
													decoding: "async",
													src: Ee === "detail" && I.view_url || I.preview_url,
													alt: `${ee(I)}的设计预览`
												}, `${k?.id}:${I.id}:${Ee}`)
											}), /* @__PURE__ */ (0, C.jsxs)("div", {
												className: "ribbon-tools",
												children: [
													/* @__PURE__ */ (0, C.jsxs)("div", {
														className: "ribbon-zoom",
														role: "group",
														"aria-label": "预览缩放",
														children: [/* @__PURE__ */ (0, C.jsx)("button", {
															type: "button",
															className: Ee === "detail" ? "is-active" : "",
															"aria-pressed": Ee === "detail",
															onClick: () => De("detail"),
															children: "细节"
														}), /* @__PURE__ */ (0, C.jsx)("button", {
															type: "button",
															className: Ee === "fit" ? "is-active" : "",
															"aria-pressed": Ee === "fit",
															onClick: () => De("fit"),
															children: "整条"
														})]
													}),
													/* @__PURE__ */ (0, C.jsx)("span", {
														className: "ribbon-metrics",
														children: Ut
													}),
													/* @__PURE__ */ (0, C.jsx)("span", {
														className: "ribbon-hint",
														children: Ee === "detail" ? "左右拖动查看整条" : ""
													})
												]
											})] }) : /* @__PURE__ */ (0, C.jsxs)("div", {
												className: "empty-canvas",
												children: [/* @__PURE__ */ (0, C.jsx)("h3", { children: "首稿预览" }), z && /* @__PURE__ */ (0, C.jsxs)("div", {
													className: "template-peek",
													children: [/* @__PURE__ */ (0, C.jsx)(Se, {
														src: _n(z),
														alt: "当前排版参考"
													}), /* @__PURE__ */ (0, C.jsxs)("span", { children: [z.name, " · 排版参考"] })]
												})]
											}),
											Lt && /* @__PURE__ */ (0, C.jsxs)("div", {
												className: "processing-overlay",
												role: "status",
												children: [
													/* @__PURE__ */ (0, C.jsx)("span", { className: "spinner" }),
													/* @__PURE__ */ (0, C.jsx)("strong", { children: Ce[Me?.phase || ""] || Me?.phase || "正在处理设计…" }),
													/* @__PURE__ */ (0, C.jsx)("span", { children: "完成后自动更新，已有版本仍可下载" })
												]
											})
										]
									}),
									I ? /* @__PURE__ */ (0, C.jsxs)(C.Fragment, { children: [(Rt || I.provider === "test") && /* @__PURE__ */ (0, C.jsx)("div", {
										className: "preview-caption",
										children: /* @__PURE__ */ (0, C.jsx)("span", { children: Rt ? "正在查看历史保存版本" : "测试模式结果" })
									}), Rt && /* @__PURE__ */ (0, C.jsxs)("div", {
										className: "history-hint",
										children: ["历史预览不改变当前版本。", /* @__PURE__ */ (0, C.jsx)("button", {
											onClick: () => Te(k.current_version_id),
											children: "返回当前版本"
										})]
									})] }) : null
								]
							}), !!k?.versions?.length && /* @__PURE__ */ (0, C.jsxs)("details", {
								className: "panel history-panel",
								children: [/* @__PURE__ */ (0, C.jsxs)("summary", {
									className: "history-heading",
									children: [
										"版本记录（",
										k.versions.length,
										"）"
									]
								}), k?.versions?.length ? /* @__PURE__ */ (0, C.jsx)("div", {
									className: "version-grid",
									children: k.versions.map((e) => /* @__PURE__ */ (0, C.jsxs)("button", {
										className: `version-card ${e.id === I?.id ? "selected" : ""}`,
										onClick: () => Te(e.id),
										"aria-pressed": e.id === I?.id,
										children: [
											/* @__PURE__ */ (0, C.jsx)(Se, {
												src: e.preview_url,
												loading: "lazy",
												decoding: "async",
												alt: `${ee(e)}缩略图`
											}),
											/* @__PURE__ */ (0, C.jsxs)("div", { children: [/* @__PURE__ */ (0, C.jsx)("strong", { children: ee(e) }), e.id === k.current_version_id ? /* @__PURE__ */ (0, C.jsx)("span", {
												className: "tiny-pill",
												children: "当前"
											}) : /* @__PURE__ */ (0, C.jsxs)("small", { children: ["V", e.sequence] })] }),
											/* @__PURE__ */ (0, C.jsxs)("small", {
												className: "version-parent",
												children: [e.parent_version_id ? `基于 V${k.versions.find((t) => t.id === e.parent_version_id)?.sequence ?? "?"}` : "初始版本", e.prompt ? ` · ${e.prompt}` : ""]
											})
										]
									}, e.id))
								}) : /* @__PURE__ */ (0, C.jsxs)("div", {
									className: "empty-history",
									children: [
										/* @__PURE__ */ (0, C.jsx)("span", { className: "history-line" }),
										/* @__PURE__ */ (0, C.jsx)("span", { children: "生成首稿后，版本将保存在这里" }),
										/* @__PURE__ */ (0, C.jsx)("span", { className: "history-line" })
									]
								})]
							}, k.id)]
						}),
						F && /* @__PURE__ */ (0, C.jsxs)("aside", {
							className: "panel refinement-panel",
							children: [
								/* @__PURE__ */ (0, C.jsxs)("div", {
									className: "panel-heading",
									children: [/* @__PURE__ */ (0, C.jsx)("div", { children: /* @__PURE__ */ (0, C.jsx)("h2", { children: "文字精修" }) }), /* @__PURE__ */ (0, C.jsx)(O, { name: "spark" })]
								}),
								/* @__PURE__ */ (0, C.jsxs)("p", {
									className: "remaining-edits",
									children: [
										"本作品还可精修 ",
										/* @__PURE__ */ (0, C.jsx)("strong", { children: It }),
										" 次"
									]
								}),
								/* @__PURE__ */ (0, C.jsxs)("div", {
									className: "refinement-body",
									children: [
										/* @__PURE__ */ (0, C.jsx)("label", {
											htmlFor: "refinement",
											children: "告诉我们，你想怎么改"
										}),
										Vt && F && !Rt && /* @__PURE__ */ (0, C.jsxs)("label", {
											className: "target-picker",
											children: ["精修范围", /* @__PURE__ */ (0, C.jsxs)("select", {
												"aria-label": "精修范围",
												disabled: R || Zt || It === 0,
												value: qe,
												onChange: (e) => Je(e.target.value),
												children: [
													/* @__PURE__ */ (0, C.jsx)("option", {
														value: "layout",
														children: "整个布局"
													}),
													/* @__PURE__ */ (0, C.jsx)("option", {
														value: "background",
														disabled: !!Kt.length && Kt.every((e) => F.snapshot.zone_background_refs?.[e] || F.snapshot.zone_colors?.[e]),
														children: "共用底纹"
													}),
													(F.snapshot.pattern_slots || []).map((e, t) => /* @__PURE__ */ (0, C.jsx)("option", {
														value: e,
														children: `图案 ${t + 1} · ${Wt.get(F.snapshot.asset_refs[t])?.name || "已保存图案"}（全部副本）`
													}, e)),
													(ge[F.snapshot.template_mode] || []).map((e) => /* @__PURE__ */ (0, C.jsxs)("option", {
														value: `zone:${e}`,
														children: [he[e], "底纹"]
													}, e)),
													F.snapshot.border_ref && /* @__PURE__ */ (0, C.jsx)("option", {
														value: "border",
														children: "上下边饰"
													})
												]
											})]
										}),
										/* @__PURE__ */ (0, C.jsx)("textarea", {
											id: "refinement",
											value: Oe,
											onChange: (e) => ke(e.target.value),
											maxLength: 2e3,
											disabled: !F || R || It === 0 || Rt,
											placeholder: hn ? "例如：把图案缩小一些，间距拉开一点，保留现在的底色。" : "例如：把图案缩小一些，保留现在的底色。"
										}),
										/* @__PURE__ */ (0, C.jsxs)("div", {
											className: "text-limit",
											children: [Oe.length, " / 2000"]
										}),
										/* @__PURE__ */ (0, C.jsxs)("button", {
											className: "primary full refine-button",
											"aria-describedby": Yt ? "ribbon-layout-issue" : void 0,
											disabled: !F || R || It === 0 || Rt || !Xt || pn || !Oe.trim() && !Zt,
											onClick: () => void Tn(),
											children: [Lt ? /* @__PURE__ */ (0, C.jsx)("span", { className: "spinner tiny" }) : /* @__PURE__ */ (0, C.jsx)(O, { name: "spark" }), Re && Ge ? "正在提交…" : Lt ? "正在处理…" : It === 0 ? "精修次数已用完" : "开始精修"]
										}),
										/* @__PURE__ */ (0, C.jsx)("p", {
											className: "refine-help",
											children: F ? Rt ? "请返回当前版本后继续精修。" : It === 0 ? "仍可查看历史、回退和下载。" : an ? fn?.allowed_operations.length === 0 && !un ? "当前版本不支持直接修改，请重新选择素材与排版后应用。" : Zt ? "本次将同时应用左侧的素材与排版选择。" : "成功完成后计一次，系统失败不扣次。" : Zt ? "AI 尚未配置；清空文字可仅应用所选素材与排版，成功后计一次。" : "AI 尚未配置，仍可查看、下载或更换素材后应用所选配置。" : "先生成首稿，再开始细化你的设计。"
										}),
										/* @__PURE__ */ (0, C.jsxs)("div", {
											className: "suggestions",
											children: [/* @__PURE__ */ (0, C.jsx)("span", { children: rn ? "测试示例" : "可用示例" }), gn.map((e) => /* @__PURE__ */ (0, C.jsxs)("button", {
												disabled: !F || R || It === 0 || Rt || !an,
												onClick: () => ke(e),
												children: [e, /* @__PURE__ */ (0, C.jsx)(O, {
													name: "plus",
													size: 13
												})]
											}, e))]
										})
									]
								}),
								/* @__PURE__ */ (0, C.jsxs)("div", {
									className: "refine-footer",
									children: [/* @__PURE__ */ (0, C.jsxs)("details", {
										className: "model-workflow-help",
										children: [
											/* @__PURE__ */ (0, C.jsx)("summary", { children: "精修说明" }),
											fn && !fn.composite_edit && /* @__PURE__ */ (0, C.jsx)("p", {
												className: "model-edit-boundary",
												children: fn.composite_edit_reason
											}),
											/* @__PURE__ */ (0, C.jsx)("p", { children: "DeepSeek 根据文字和所选图案的名称、顺序理解要求；当前不把图片发给它审图。对象不明确时请补充说明。" }),
											/* @__PURE__ */ (0, C.jsx)("p", { children: "Seedream 负责生成底图、修改图案或底图；程序负责原尺寸排版、版本与下载。首稿使用原素材，不由模型重画。" }),
											/* @__PURE__ */ (0, C.jsx)("p", { children: "每次成功精修计一次。回退到父版本保留累计次数。" })
										]
									}), rn && /* @__PURE__ */ (0, C.jsx)("p", {
										className: "test-limit",
										children: "测试替身仅支持已列明的参数与内容示例。其他要求会提示补充说明，真实 AI 尚未接通。"
									})]
								})
							]
						})
					]
				}),
				/* @__PURE__ */ (0, C.jsx)("footer", {
					className: "page-footer",
					children: /* @__PURE__ */ (0, C.jsxs)("span", { children: [
						"个人作品与素材保留 ",
						w?.retention_hours ?? 50,
						" 小时，请及时下载。"
					] })
				})
			] }),
			We === "layouts" && /* @__PURE__ */ (0, C.jsxs)(le, {
				title: "选择排版模式",
				onClose: () => P(null),
				wide: !0,
				className: "layout-picker-modal",
				children: [
					/* @__PURE__ */ (0, C.jsx)("p", {
						className: "muted library-note",
						children: "选择排法后点击完成。案例只作排版参考，正式规格由内部配置决定。"
					}),
					/* @__PURE__ */ (0, C.jsx)("div", {
						className: "layout-picker-grid template-grid",
						children: en.map(vn)
					}),
					/* @__PURE__ */ (0, C.jsxs)("div", {
						className: "modal-footer",
						children: [/* @__PURE__ */ (0, C.jsxs)("span", { children: ["已选：", z?.name || "尚未选择排版"] }), /* @__PURE__ */ (0, C.jsxs)("button", {
							className: "primary",
							onClick: () => P(null),
							children: ["完成选择", /* @__PURE__ */ (0, C.jsx)(O, {
								name: "check",
								size: 16
							})]
						})]
					})
				]
			}),
			at && n && r === "ribbon" && /* @__PURE__ */ (0, C.jsx)(le, {
				title: at.mode ? `${at.name} · 案例` : "全部排版案例",
				onClose: () => ot(null),
				wide: !0,
				className: "layout-examples-modal",
				children: /* @__PURE__ */ (0, C.jsx)(ce, {
					mode: at.mode,
					cache: Ct,
					onUnauthorized: t,
					onViewAll: () => ot({
						mode: null,
						name: "全部排版案例"
					}),
					referenceMode: z?.mode,
					legacyLayout: !Ht,
					onChooseReference: cn && !R && !L ? (e) => {
						z && d(e, z.mode) && (St({
							code: e.code,
							mode: z.mode
						}), ot(null));
					} : void 0
				})
			}),
			(We === "pattern" || We === "background") && /* @__PURE__ */ (0, C.jsxs)(le, {
				title: Ye === "border" ? "选择边饰" : Ye ? he[Ye] + "底纹" : We === "pattern" ? "图案素材库" : "底图素材库",
				onClose: () => P(null),
				wide: !0,
				className: "asset-library-modal",
				children: [
					/* @__PURE__ */ (0, C.jsxs)("div", {
						className: "library-toolbar",
						children: [/* @__PURE__ */ (0, C.jsx)("input", {
							"aria-label": "搜索素材",
							placeholder: "搜索素材名称…",
							value: Ze,
							onChange: (e) => Qe(e.target.value)
						}), !Ye && /* @__PURE__ */ (0, C.jsxs)("label", {
							className: `secondary upload-label ${$e ? "disabled" : ""}`,
							children: [
								/* @__PURE__ */ (0, C.jsx)(O, { name: "upload" }),
								$e ? `上传 ${tt?.completed || 0}/${tt?.total || 0}` : "上传素材",
								/* @__PURE__ */ (0, C.jsx)("input", {
									ref: Et,
									type: "file",
									accept: "image/png,image/jpeg,image/webp",
									multiple: !0,
									hidden: !0,
									disabled: $e || R,
									onChange: (e) => void Pn(e.target.files, We)
								})
							]
						})]
					}),
					Ft && /* @__PURE__ */ (0, C.jsxs)("label", {
						className: "checkbox-line",
						children: [/* @__PURE__ */ (0, C.jsx)("input", {
							type: "checkbox",
							checked: rt,
							disabled: R,
							onChange: (e) => it(e.target.checked)
						}), "上传为共享素材，供所有账号使用"]
					}),
					/* @__PURE__ */ (0, C.jsxs)("p", {
						className: "muted library-note",
						children: [
							We === "pattern" ? "可选择多个已处理好的图案。" : "选择一种底图，作为设计背景。",
							" ",
							"标记“演示”的素材仅供联调。"
						]
					}),
					/* @__PURE__ */ (0, C.jsx)("div", {
						className: "library-grid",
						children: Vn.map((e) => {
							let t = Ye ? (Ye === "border" ? j.border_ref : j.zone_background_refs?.[Ye]) === e.id : We === "pattern" ? j.asset_ids.includes(e.id) : j.background_id === e.id;
							return /* @__PURE__ */ (0, C.jsxs)("div", {
								className: "library-item",
								children: [/* @__PURE__ */ (0, C.jsxs)("button", {
									className: `library-card ${t ? "selected" : ""}`,
									disabled: R,
									"aria-pressed": t,
									onClick: () => Ye === "border" ? yn({
										...j,
										border_ref: e.id
									}) : Ye ? yn({
										...j,
										zone_background_refs: {
											...j.zone_background_refs,
											[Ye]: e.id
										}
									}) : We === "pattern" ? Fn(e.id) : yn({
										...j,
										background_id: e.id
									}),
									children: [
										/* @__PURE__ */ (0, C.jsxs)("div", {
											className: `library-image ${We === "pattern" ? "checker" : ""}`,
											children: [/* @__PURE__ */ (0, C.jsx)(Se, {
												src: e.thumbnail_url || e.url,
												alt: e.name,
												loading: "lazy",
												decoding: "async"
											}), t && /* @__PURE__ */ (0, C.jsx)("span", {
												className: "check-mark",
												children: /* @__PURE__ */ (0, C.jsx)(O, {
													name: "check",
													size: 14
												})
											})]
										}),
										/* @__PURE__ */ (0, C.jsx)("strong", { children: e.name }),
										/* @__PURE__ */ (0, C.jsxs)("span", { children: [e.is_demo ? "演示 · " : "", e.shared ? "共享素材" : "私有素材"] })
									]
								}), (!e.shared || Ft) && /* @__PURE__ */ (0, C.jsx)("button", {
									className: "hide-asset",
									disabled: R,
									onClick: () => void In(e),
									children: "从素材库移除"
								})]
							}, e.id);
						})
					}),
					!Rn.length && /* @__PURE__ */ (0, C.jsx)("div", {
						className: "empty-library",
						children: "没有找到素材，可上传新的图案或底图。"
					}),
					Rn.length > 36 && /* @__PURE__ */ (0, C.jsxs)("nav", {
						className: "library-pagination",
						"aria-label": "素材分页",
						children: [
							/* @__PURE__ */ (0, C.jsx)("button", {
								className: "secondary small",
								disabled: Bn === 0,
								onClick: () => ct(Bn - 1),
								children: "上一页"
							}),
							/* @__PURE__ */ (0, C.jsxs)("span", {
								role: "status",
								children: [
									"第 ",
									Bn + 1,
									" / ",
									zn,
									" 页 · 共 ",
									Rn.length,
									" 项"
								]
							}),
							/* @__PURE__ */ (0, C.jsx)("button", {
								className: "secondary small",
								disabled: Bn + 1 >= zn,
								onClick: () => ct(Bn + 1),
								children: "下一页"
							})
						]
					}),
					/* @__PURE__ */ (0, C.jsxs)("div", {
						className: "modal-footer",
						children: [/* @__PURE__ */ (0, C.jsx)("span", { children: Ye ? Ye === "border" ? "选择一个完整边饰" : "选择该区域的底纹" : We === "pattern" ? `已选 ${j.asset_ids.length} 个图案` : $t ? `已选：${$t.name}` : "尚未选择底图" }), /* @__PURE__ */ (0, C.jsxs)("button", {
							className: "primary",
							onClick: () => P(null),
							children: ["完成选择", /* @__PURE__ */ (0, C.jsx)(O, {
								name: "check",
								size: 16
							})]
						})]
					})
				]
			}),
			We === "designs" && /* @__PURE__ */ (0, C.jsxs)(le, {
				title: "我的作品",
				onClose: () => {
					P(null), ft(null);
				},
				wide: !0,
				className: "design-library-modal",
				children: [
					/* @__PURE__ */ (0, C.jsxs)("div", {
						className: "design-list-tabs",
						role: "group",
						"aria-label": "作品列表",
						children: [/* @__PURE__ */ (0, C.jsx)("button", {
							className: ht ? "" : "selected",
							onClick: () => {
								gt(!1), ft(null);
							},
							children: "我的作品"
						}), /* @__PURE__ */ (0, C.jsx)("button", {
							className: ht ? "selected" : "",
							onClick: () => {
								gt(!0), ft(null), An();
							},
							children: "已删除作品"
						})]
					}),
					dt && /* @__PURE__ */ (0, C.jsxs)("div", {
						className: "delete-design-confirm",
						role: "alert",
						children: [/* @__PURE__ */ (0, C.jsxs)("p", { children: [
							"删除“",
							dt.name,
							"”？删除后保留 ",
							w?.retention_hours ?? 50,
							" 小时，可恢复；已有下载仍绑定原版本。"
						] }), /* @__PURE__ */ (0, C.jsxs)("div", { children: [/* @__PURE__ */ (0, C.jsx)("button", {
							className: "secondary small",
							disabled: Re,
							onClick: () => ft(null),
							children: "取消"
						}), /* @__PURE__ */ (0, C.jsx)("button", {
							className: "danger-button",
							disabled: Re,
							onClick: () => void jn(dt),
							children: "确认删除"
						})] })]
					}),
					u && !ht && /* @__PURE__ */ (0, C.jsx)("p", {
						role: "status",
						children: "正在更新作品列表…"
					}),
					v && !ht && /* @__PURE__ */ (0, C.jsxs)("div", {
						className: "notice error",
						role: "alert",
						children: [/* @__PURE__ */ (0, C.jsx)("span", { children: v }), /* @__PURE__ */ (0, C.jsx)("button", {
							className: "secondary small",
							onClick: () => void kn(),
							children: "重试读取作品"
						})]
					}),
					_t && ht && /* @__PURE__ */ (0, C.jsx)("p", {
						role: "status",
						children: "正在读取已删除作品…"
					}),
					/* @__PURE__ */ (0, C.jsx)("div", {
						className: "design-library",
						children: (ht ? pt : oe).map((e) => /* @__PURE__ */ (0, C.jsxs)("div", {
							className: "design-list-row",
							children: [/* @__PURE__ */ (0, C.jsxs)("button", {
								disabled: Re || !!Ge || L || $e,
								className: `design-list-item ${e.id === k?.id ? "selected" : ""}`,
								onClick: () => ht ? void Mn(e) : void On(e.id),
								"aria-label": ht ? `恢复${e.name}` : void 0,
								children: [
									/* @__PURE__ */ (0, C.jsx)("span", {
										className: "design-list-icon",
										children: /* @__PURE__ */ (0, C.jsx)(O, {
											name: "folder",
											size: 23
										})
									}),
									/* @__PURE__ */ (0, C.jsxs)("div", { children: [/* @__PURE__ */ (0, C.jsx)("strong", { children: e.name }), /* @__PURE__ */ (0, C.jsxs)("small", { children: [
										e.current_version_id ? "已有保存版本" : "尚未生成首稿",
										" · 已精修 ",
										e.successful_refinement_count,
										" / 2 次"
									] })] }),
									e.active_job_id && /* @__PURE__ */ (0, C.jsx)("span", {
										className: "tiny-pill",
										children: "处理中"
									}),
									ht ? /* @__PURE__ */ (0, C.jsx)("span", { children: "恢复" }) : /* @__PURE__ */ (0, C.jsx)(O, { name: "arrow" })
								]
							}), !ht && /* @__PURE__ */ (0, C.jsx)("button", {
								type: "button",
								className: "delete-design-button",
								"aria-label": `删除${e.name}`,
								title: e.active_job_id ? "作品正在处理，完成后可删除" : `删除${e.name}`,
								disabled: Re || !!Ge || $e || L || !!lt?.loading || !!e.active_job_id,
								onClick: () => ft(e),
								children: "删除"
							})]
						}, e.id))
					}),
					!(ht ? pt : oe).length && !_t && /* @__PURE__ */ (0, C.jsx)("div", {
						className: "empty-library",
						children: ht ? "没有可恢复的已删除作品。" : "你的第一份作品，即将从这里开始。"
					}),
					/* @__PURE__ */ (0, C.jsxs)("div", {
						className: "modal-footer",
						children: [/* @__PURE__ */ (0, C.jsx)("span", { children: ht ? `删除后保留 ${w?.retention_hours ?? 50} 小时，可恢复` : "作品、额度和版本均保存在服务端" }), /* @__PURE__ */ (0, C.jsxs)("button", {
							className: "primary",
							disabled: Re || !!Ge || L || $e,
							onClick: () => void Dn(),
							children: [/* @__PURE__ */ (0, C.jsx)(O, { name: "plus" }), "新建作品"]
						})]
					})
				]
			}),
			We === "admin" && Ft && /* @__PURE__ */ (0, C.jsx)(ie, {
				onClose: () => P(null),
				onChanged: xn
			})
		]
	});
}
// src/styles.css?inline
var M = ":host{color:#233d35;font-synthesis:none;--green:#215b4d;--deep:#163d33;--pale:#edf3e9;--line:#e3e9e2;--muted:#839087;--gold:#b7a66a;--radius:16px;background:#f7f8f4;min-width:0;font-family:Noto Sans SC,Microsoft YaHei,sans-serif;font-size:14px;font-weight:400;line-height:1.55;display:block;container-type:inline-size}*{box-sizing:border-box}.app-shell{min-width:0;margin:0}button,input,textarea,select{font:inherit}button,a,input,textarea,select{-webkit-tap-highlight-color:transparent}button{cursor:pointer}button:disabled{cursor:not-allowed;opacity:.45}button,a{transition:background .16s,border-color .16s,box-shadow .16s,transform .16s}button:focus-visible,a:focus-visible,input:focus-visible,textarea:focus-visible,select:focus-visible{outline-offset:3px;outline:3px solid #a6c6a8}button{color:inherit}a{color:inherit;text-decoration:none}img{max-width:100%;display:block}h1,h2,h3,p{margin:0}h1,h2,h3{font-weight:650}h3{font-size:14px}button svg,a svg{flex-shrink:0}input,textarea,select{width:100%;color:var(--deep);background:#fff;border:1px solid #dfe6df;border-radius:8px;padding:11px 12px}input:focus,textarea:focus,select:focus{border-color:#7ba28c;outline:none}textarea{resize:vertical}input[type=checkbox]{width:15px;height:15px;accent-color:var(--green)}small{font-size:11px}.muted{color:var(--muted)}.microcopy{color:#7c8a80;font-size:11px;line-height:1.8}.eyebrow,.step-label{letter-spacing:1.9px;color:#94a395;font-size:10px;font-weight:500}.primary,.secondary,.text-button,.icon-button{white-space:nowrap;border:0;border-radius:8px;justify-content:center;align-items:center;gap:8px;font-weight:550;display:inline-flex}.primary{background:var(--green);color:#fff;border:1px solid var(--green);padding:13px 22px}.primary:hover:not(:disabled){background:#174b3f;box-shadow:0 4px 14px #184f3c16}.secondary{background:#fff;border:1px solid #dce4dc;padding:10px 16px;font-size:12px}.secondary:hover:not(:disabled){background:#fafcf8;border-color:#8fae99}.text-button{background:0 0;padding:7px;font-size:12px}.text-button:hover{background:#edf1e9}.icon-button{color:#7b8980;background:0 0;flex-shrink:0;width:32px;height:32px}.icon-button:hover{color:var(--green);background:#e9f0e5}.full{width:100%}.small{padding:7px 11px;font-size:11px}.tiny-pill{color:#52735b;white-space:nowrap;background:#edf3e9;border-radius:4px;padding:2px 6px;font-size:10px}.outline-pill{color:#8b8e72;white-space:nowrap;border:1px solid #dddfcf;border-radius:4px;padding:3px 9px;font-size:10px}.spinner{border:2px solid #becfbe;border-top-color:var(--green);border-radius:50%;flex-shrink:0;width:25px;height:25px;animation:.8s linear infinite spin;display:inline-block}.spinner.tiny{width:16px;height:16px}.primary .spinner{border-color:#fff #ffffff45 #ffffff45}@keyframes spin{to{transform:rotate(360deg)}}.page-loader{color:#7a897f;justify-content:center;align-items:center;gap:14px;min-height:90vh;display:flex}.page-loader.in-page{min-height:430px}.notice{border:1px solid;border-radius:8px;justify-content:space-between;align-items:center;gap:14px;margin-bottom:14px;padding:10px 15px;font-size:12px;display:flex}.notice.error{color:#945d41;background:#fff4ef;border-color:#eddbc9}.notice.success{color:#477047;background:#edf5e9;border-color:#dbe8d2}.notice.info{color:#536c7e;background:#f0f4f7;border-color:#dfe7ef}.topbar{background:#fff;border-bottom:1px solid #e6eae1;justify-content:space-between;align-items:center;min-height:64px;padding:12px 20px;display:flex}.brand{align-items:center;gap:10px;display:flex}.brand-icon{color:var(--green);justify-content:center;align-items:center;display:flex}.brand strong{letter-spacing:1px;font-size:20px;line-height:1.5;display:block}.brand small{letter-spacing:2px;color:#94a38f;font-size:8px;font-weight:500;display:block}.version-tag{color:#77906c;border:1px solid #dce3d7;border-radius:4px;align-self:flex-start;margin-top:6px;margin-left:3px;padding:1px 5px;font-size:9px}.header-actions{color:#627268;align-items:center;gap:15px;display:flex}.header-divider{background:#e4e9e0;width:1px;height:24px;margin:0 5px}.count{background:#eef2e9;border-radius:4px;padding:1px 5px;font-size:9px}.avatar{color:#638059;background:#e6eddf;border-radius:50%;justify-content:center;align-items:center;width:29px;height:29px;font-size:12px;display:flex}.user-name{margin-left:-8px;font-size:12px}.app-shell main{max-width:1700px;margin:auto;padding:20px 20px 12px}.workspace-title{justify-content:space-between;align-items:center;margin-bottom:24px;display:flex}.workspace-title h1{letter-spacing:.2px;margin:4px 0;font-size:27px;line-height:1.7}.workspace-title p{color:#8a968b;font-size:12px}.title-dot{color:#b8c59f}.workspace-title>.secondary{margin-top:9px}.environment-strip{color:#91957f;background:#f0f2e8;border:1px solid #e4e7d8;border-radius:7px;justify-content:space-between;align-items:center;gap:15px;margin-bottom:21px;padding:10px 14px;font-size:10px;display:flex}.environment-strip>div{align-items:center;gap:8px;display:flex}.environment-strip strong{color:#7f8268;font-weight:500}.status-dot{background:#6b956d;border-radius:50%;flex-shrink:0;width:6px;height:6px;display:inline-block}.status-dot.amber{background:#baab70}.workspace-grid{grid-template-columns:294px minmax(350px,1fr) 290px;align-items:start;gap:20px;display:grid}.panel{border:1px solid var(--line);border-radius:var(--radius);background:#fff;overflow:hidden;box-shadow:0 2px 5px #274c2402}.panel-heading{justify-content:space-between;align-items:center;gap:9px;padding:22px 23px 0;display:flex}.panel-heading h2{letter-spacing:.3px;text-overflow:ellipsis;white-space:nowrap;max-width:320px;margin-top:4px;font-size:17px;overflow:hidden}.panel-heading>svg{color:#a6b49b}.source-panel .panel-heading{margin-bottom:3px}.source-section{border-bottom:1px solid #edf0e9;padding:21px 22px}.source-section:last-of-type{border:0}.section-label{justify-content:space-between;align-items:center;margin-bottom:12px;display:flex}.section-label h3{font-size:13px}.section-label>span{color:#a0aa9c;font-size:10px}.two-actions{grid-template-columns:1fr 1fr;gap:9px;display:grid}.two-actions .secondary{padding:9px 5px;font-size:11px}.selected-patterns{grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:13px;display:grid}.pattern-tile .checker{background-color:#f9fbf5;border:1px solid #e8ece4;border-radius:7px;justify-content:center;align-items:center;height:64px;padding:10px;display:flex;position:relative}.checker{background-image:linear-gradient(45deg,#e9ede31a 25%,#0000 25%),linear-gradient(-45deg,#e9ede333 25%,#0000 25%),linear-gradient(45deg,#0000 75%,#e9ede333 75%),linear-gradient(-45deg,#0000 75%,#e9ede333 75%);background-position:0 0,0 6px,6px -6px,-6px 0;background-size:12px 12px}.pattern-tile img{object-fit:contain;width:46px;height:46px}.pattern-tile>span{text-align:center;white-space:nowrap;text-overflow:ellipsis;color:#677b68;margin-top:6px;font-size:10px;display:block;overflow:hidden}.remove-asset{color:#73906e;background:#fff;border:0;border-radius:50%;justify-content:center;align-items:center;width:17px;height:17px;padding:0;font-size:14px;line-height:1;display:flex;position:absolute;top:3px;right:3px}.remove-asset:hover{background:#e2ebda}.empty-patterns{color:#9aaa91;background:#fafcf7;border:1px dashed #d8e2d1;border-radius:8px;flex-direction:column;align-items:center;gap:6px;width:100%;margin-top:13px;padding:18px 8px;display:flex}.empty-patterns span{font-size:10px}.empty-patterns small{color:#b0baaa;font-size:9px}.template-grid{grid-template-columns:1fr 1fr;gap:9px;display:grid}.template-card{background:#fff;border:1px solid #e2e8df;border-radius:7px;min-width:0;padding:6px;position:relative;overflow:hidden}.template-card img{object-fit:cover;opacity:.85;border-radius:3px;width:100%;height:42px}.template-card>span{color:#82927d;justify-content:center;align-items:center;gap:6px;padding:6px 0 2px;font-size:11px;display:flex}.template-card.selected{background:#fbfcf8;border-color:#648666;box-shadow:inset 0 0 0 1px #648666}.template-card.selected>span{color:#3d6546;font-weight:600}.template-card:hover:not(:disabled){border-color:#719774}.background-selected{background:#f4f7ee;border:1px solid #e3e9db;border-radius:7px;align-items:center;gap:10px;margin-top:12px;padding:9px;display:flex}.background-selected img{object-fit:cover;border-radius:4px;width:39px;height:34px}.background-selected>div{flex:1;min-width:0}.background-selected strong{white-space:nowrap;text-overflow:ellipsis;font-size:11px;font-weight:500;display:block;overflow:hidden}.background-selected small{color:#95a28d;margin-top:2px;font-size:9px;display:block}.background-selected>svg{color:#799371}.empty-background{color:#a3ac9c;text-align:center;padding:17px 4px 0;font-size:10px}.background-section .microcopy{margin-top:9px}.selection-warning{color:#aa8650;background:#fff6e8;border-radius:7px;margin:0 15px 18px;padding:10px;font-size:11px;line-height:1.8}.center-column{flex-direction:column;gap:17px;min-width:0;display:flex}.preview-panel{padding-bottom:22px}.preview-panel .panel-heading{padding:22px 24px 20px}.state-pill{color:#7c9672;white-space:nowrap;background:#f1f6ec;border-radius:5px;align-items:center;gap:5px;padding:5px 8px;font-size:9px;display:inline-flex}.state-pill.working{color:#a58c55;background:#f6f2e6}.state-pill.working .status-dot{background:#bfa363}.preview-stage{background-color:#f5f7ef;background-image:linear-gradient(#e7ebdf55 5%,#eff2e700 5%),linear-gradient(90deg,#eff2e700 95%,#e7ebdf55 95%);background-position:0 0;background-repeat:repeat;background-size:20px 20px;background-attachment:scroll;background-origin:padding-box;background-clip:border-box;border:1px solid #e6eadd;border-radius:10px;flex-direction:column;min-height:330px;margin:0 23px;display:flex;position:relative;overflow:hidden}.stage-topline,.stage-bottomline{color:#a4b095;justify-content:space-between;align-items:center;padding:14px 15px;font-size:9px;display:flex}.stage-topline>span:first-child{color:#899f79;font-size:10px}.stage-bottomline{letter-spacing:1px;margin-top:auto;font-size:8px}.stage-bottomline>span:first-child{letter-spacing:.2px}.preview-stage.is-filled{min-height:0}.ribbon-display{scrollbar-width:thin;scrollbar-color:#cfd8c2 transparent;flex:1;align-items:center;min-height:0;padding:18px 0;display:flex;overflow:auto hidden}.ribbon-display::-webkit-scrollbar{height:6px}.ribbon-display::-webkit-scrollbar-thumb{background:#cfd8c2;border-radius:3px}.ribbon-display img{border-radius:2px;flex:none;display:block;box-shadow:0 7px 12px #3351350a}.ribbon-display.detail img{width:auto;max-width:none;height:168px}.ribbon-display.fit img{width:100%;height:auto;max-height:none}.ribbon-tools{color:#94a385;align-items:center;gap:12px;padding:0 15px 14px;font-size:10px;display:flex}.ribbon-zoom{border:1px solid #dfe5d5;border-radius:6px;flex:none;display:inline-flex;overflow:hidden}.ribbon-zoom button{color:#7d8f6f;cursor:pointer;background:#fff;border:0;padding:4px 10px;font-size:10px}.ribbon-zoom button.is-active{color:#4e6343;background:#eef2e6;font-weight:500}.ribbon-metrics{font-variant-numeric:tabular-nums;letter-spacing:.2px;white-space:nowrap;text-overflow:ellipsis;overflow:hidden}.ribbon-hint{white-space:nowrap;color:#b0bc9f;margin-left:auto}.preview-stage.is-empty{min-height:330px}.empty-canvas{text-align:center;flex-direction:column;flex:1;justify-content:center;align-items:center;padding:10px 15px 15px;display:flex}.empty-symbol{color:#98ad7f;background:#e9efdf;border-radius:18px;justify-content:center;align-items:center;width:56px;height:56px;margin-bottom:12px;display:flex}.empty-canvas h3{color:#839575;font-size:14px;font-weight:500}.empty-canvas p{color:#a6b09a;margin-top:7px;font-size:10px;line-height:1.9}.template-peek{color:#a1af90;border-top:1px solid #e2e9d9;align-items:center;gap:8px;margin-top:15px;padding-top:12px;font-size:9px;display:flex}.template-peek img{object-fit:cover;opacity:.65;border-radius:3px;width:85px;height:24px}.processing-overlay{-webkit-backdrop-filter:blur(3px);backdrop-filter:blur(3px);background:#f8faf1d9;flex-direction:column;justify-content:center;align-items:center;gap:10px;display:flex;position:absolute;inset:0}.processing-overlay strong{font-size:13px;font-weight:500}.processing-overlay>span:last-child{color:#91a086;font-size:10px}.preview-caption{color:#a4af9a;justify-content:space-between;align-items:center;padding:11px 24px 0;font-size:9px;display:flex}.preview-caption>span:first-child{align-items:center;gap:5px;display:flex}.result-actions{grid-template-columns:1fr 1fr;gap:12px;padding:19px 23px 0;display:grid}.result-actions .primary,.result-actions .secondary{padding:12px 8px;font-size:12px}.generate-area{padding:20px 23px 0}.generate-area>.primary{font-size:13px}.generate-area>.primary svg:last-child{margin-left:auto}.generate-area>.primary svg:first-child{margin-right:auto}.generate-area>small{text-align:center;color:#9eaa94;padding-top:10px;font-size:10px;display:block}.history-hint{color:#9caa90;padding:12px 24px 0;font-size:10px}.history-hint button{color:#507644;background:0 0;border:0;padding:0 0 0 5px;font-size:10px;text-decoration:underline}.history-panel{padding:20px 22px 21px}.history-heading{justify-content:space-between;align-items:center;gap:7px;margin-bottom:16px;display:flex}.history-heading h3{font-size:13px}.history-heading>span{color:#a9b19f;font-size:9px}.version-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;display:grid}.version-card{text-align:left;background:#fff;border:1px solid #e5eadf;border-radius:8px;min-width:0;padding:8px}.version-card.selected{background:#fcfdf9;border-color:#7a9969;box-shadow:inset 0 0 0 1px #7a9969}.version-card>img{object-fit:cover;background:#f4f6ed;border-radius:3px;width:100%;height:46px}.version-card>div{justify-content:space-between;align-items:center;gap:5px;margin-top:8px;display:flex}.version-card strong{font-size:11px;font-weight:500}.version-card>div>small{color:#a9b19d;font-size:9px}.version-card .tiny-pill{padding:1px 5px;font-size:8px}.version-parent{white-space:nowrap;text-overflow:ellipsis;color:#a8b29c;margin-top:5px;font-size:8px;display:block;overflow:hidden}.empty-history{color:#aab69f;justify-content:center;align-items:center;gap:12px;min-height:63px;font-size:10px;display:flex}.history-line{background:#e2e9d9;width:25px;height:1px}.handoff-note{color:#9baa92;align-items:center;gap:11px;padding:1px 9px;display:flex}.note-icon{color:#94a681;background:#eaf0e2;border-radius:50%;flex-shrink:0;justify-content:center;align-items:center;width:34px;height:34px;display:flex}.handoff-note strong{color:#91a180;font-size:10px;font-weight:500;display:block}.handoff-note span:not(.note-icon){margin-top:2px;font-size:9px;display:block}.refinement-panel .panel-heading{padding:22px 22px 21px}.quota-card{background:#edf3e5;border:1px solid #e6eddc;border-radius:9px;margin:0 21px;padding:15px 17px 12px}.quota-card>div:first-child{justify-content:space-between;align-items:center;display:flex}.quota-card>div:first-child>span{color:#749263;font-size:11px}.quota-card strong{color:#547944;font-size:27px;font-weight:500;line-height:1}.quota-card strong small{color:#a1b48d;font-size:12px;font-weight:400}.quota-dots{gap:5px;margin-top:13px;display:flex}.quota-dots>span{background:#dfe8d5;border-radius:2px;flex:1;height:3px}.quota-dots>span.available{background:#9fbb83}.quota-card.exhausted{background:#f2f1eb;border-color:#eae8de}.refinement-body{padding:24px 21px 18px}.refinement-body>label{font-size:13px;font-weight:600}.refinement-body>p{color:#a0ac95;margin:7px 0 14px;font-size:10px;line-height:1.9}.refinement-body textarea{resize:vertical;background:#fcfdf9;border-color:#e2e9da;border-radius:8px;min-height:150px;padding:13px;font-size:11px;line-height:2.1}.refinement-body textarea::placeholder{color:#b1bba6}.refinement-body textarea:disabled{background:#f8faf4}.text-limit{text-align:right;color:#aeb9a1;margin-top:4px;font-size:8px}.suggestions{flex-direction:column;align-items:start;gap:6px;margin-top:15px;display:flex}.suggestions>span{color:#a6b099;margin-bottom:2px;font-size:9px}.suggestions>button{color:#97a587;text-align:left;background:#fcfdf9;border:1px solid #e8eddf;border-radius:5px;justify-content:space-between;align-items:center;gap:4px;width:100%;padding:6px 8px;font-size:9px;display:flex}.suggestions>button:hover:not(:disabled){color:#52753f;background:#f0f5e7;border-color:#bace9d}.refine-button{margin-top:22px;font-size:12px}.refinement-body p.refine-help{text-align:center;color:#a9b39c;margin:10px 0 0;font-size:9px;line-height:1.8}.refine-footer{background:#fdfefb;border-top:1px solid #edf0e7;padding:20px 22px}.refine-footer>div{color:#93a380;align-items:center;gap:6px;display:flex}.refine-footer strong{font-size:10px;font-weight:500}.refine-footer p{color:#a6b199;margin-top:7px;font-size:9px;line-height:1.9}.refine-footer .test-limit{color:#a8a88b;border-top:1px dashed #e7eddf;padding-top:10px}.page-footer{color:#b2bba7;justify-content:space-between;align-items:center;margin-top:29px;font-size:9px;display:flex}.page-footer>span:first-child{letter-spacing:1px}.page-footer>span:nth-child(2){letter-spacing:2px}.modal-scrim{-webkit-backdrop-filter:blur(4px);backdrop-filter:blur(4px);z-index:20;background:#16392a55;justify-content:center;align-items:center;padding:24px;display:flex;position:fixed;inset:0}.modal{background:#fff;border-radius:18px;width:520px;max-width:100%;max-height:90vh;padding:27px 30px;overflow:auto;box-shadow:0 20px 80px #142f2733}.modal-wide{width:840px}.modal-heading{justify-content:space-between;align-items:center;margin-bottom:25px;display:flex}.modal-heading h2{margin-top:5px;font-size:23px}.modal-heading .eyebrow{font-size:8px}.modal-footer{border-top:1px solid var(--line);justify-content:space-between;align-items:center;gap:15px;margin-top:22px;padding-top:20px;display:flex}.modal-footer>span{color:#8fa180;font-size:11px}.modal-footer>.primary{padding:10px 17px;font-size:12px}.library-toolbar{gap:12px;display:flex}.library-toolbar>input{flex:1;font-size:12px}.upload-label{cursor:pointer;font-size:12px}.upload-label.disabled{opacity:.5;pointer-events:none}.checkbox-line{color:#859775;align-items:center;gap:8px;margin:12px 0;font-size:11px;display:flex!important}.library-note{margin:15px 0;font-size:11px}.library-grid{grid-template-columns:repeat(4,minmax(0,1fr));gap:15px;display:grid}.library-card{text-align:left;background:#fff;border:1px solid #e2e9da;border-radius:9px;width:100%;padding:7px;overflow:hidden}.library-card.selected{background:#fafcf6;border-color:#7b9a67;box-shadow:inset 0 0 0 1px #7b9a67}.library-image{background-color:#f7f9f1;border-radius:5px;justify-content:center;align-items:center;height:100px;display:flex;position:relative}.library-image img{object-fit:contain;width:100%;max-height:100%;padding:8px}.library-image:not(.checker) img{object-fit:cover;height:100%;padding:0}.check-mark{color:#fff;background:#3b6c41;border-radius:50%;justify-content:center;align-items:center;width:20px;height:20px;display:flex;position:absolute;top:6px;right:6px}.library-card strong{text-overflow:ellipsis;white-space:nowrap;margin:9px 4px 4px;font-size:12px;font-weight:500;display:block;overflow:hidden}.library-card>span{color:#a0ad92;margin:0 4px 5px;font-size:9px;display:block}.hide-asset{color:#a5af9c;background:0 0;border:0;padding:5px 3px;font-size:9px}.hide-asset:hover{color:#a2765c}.empty-library{text-align:center;color:#9fae91;padding:45px 10px;font-size:12px}.design-library{flex-direction:column;gap:10px;display:flex}.design-list-item{text-align:left;background:#fff;border:1px solid #e4eadc;border-radius:9px;align-items:center;gap:15px;padding:15px;display:flex}.design-list-item.selected{background:#f6f9ef;border-color:#afc299}.design-list-item>div{flex:1}.design-list-item strong{font-size:13px;font-weight:500;display:block}.design-list-item small{color:#a0ae90;margin-top:4px;font-size:10px;display:block}.design-list-icon{color:#95ae79;background:#edf3e4;border-radius:10px;justify-content:center;align-items:center;width:42px;height:42px;display:flex}.design-list-item>svg{color:#a5b890}.admin-tabs{border-bottom:1px solid #e5eadf;gap:8px;margin-bottom:18px;padding-bottom:15px;display:flex}.admin-tabs button{color:#899a7b;background:0 0;border:0;border-radius:7px;padding:9px 15px;font-size:12px}.admin-tabs button.active{color:#50713a;background:#eaf2df}.admin-intro{color:#91a17f;justify-content:space-between;align-items:center;margin-bottom:16px;font-size:12px;display:flex}.table-scroll{max-height:450px;overflow:auto}.table-scroll table{border-collapse:collapse;width:100%;font-size:11px}.table-scroll th{text-align:left;color:#95a582;white-space:nowrap;background:#f5f8ed;font-size:10px;font-weight:500}.table-scroll th,.table-scroll td{border-bottom:1px solid #e9efdf;padding:12px 10px}.table-scroll td{word-break:break-word;color:#7e936a;max-width:240px}.table-scroll td strong{font-size:10px;font-weight:500;display:block}.table-scroll td small{color:#a2b48c;margin-top:4px;font-size:9px;display:block}.job-status{background:#f3f4ec;border-radius:4px;padding:3px 5px;font-size:9px}.job-status.succeeded{background:#ebf3e0}.job-status.failed{color:#a88463;background:#fff1e6}.admin-columns{grid-template-columns:1fr 1fr;gap:28px;display:grid}.admin-columns h3{margin-bottom:14px}.admin-form label{color:#849970;margin-bottom:15px;font-size:11px;display:block}.admin-form label input,.admin-form label select,.admin-form label textarea{margin-top:6px;font-size:12px}.admin-form>small{color:#a0b18a;margin-top:-8px;margin-bottom:15px;font-size:9px;display:block}.admin-form>.primary{width:100%;margin-top:12px;font-size:12px}.admin-form>.text-button{justify-content:center;width:100%;margin-top:7px;font-size:10px}.admin-form .checkbox-line input{margin:0}.code-input{font-family:Consolas,monospace}.admin-existing{max-height:530px;overflow:auto}.admin-template{text-align:left;background:#fff;border:1px solid #e4ecd9;border-radius:7px;align-items:center;gap:10px;width:100%;margin-bottom:9px;padding:9px;display:flex}.admin-template.selected{background:#f5f9ec;border-color:#acc58d}.admin-template img{object-fit:cover;border-radius:4px;width:87px;height:35px}.admin-template>div{flex:1}.admin-template strong{font-size:11px;font-weight:500;display:block}.admin-template small{color:#a4b58e;margin-top:3px;font-size:9px;display:block}.admin-template>svg{color:#a5b58e}.profile-item{border:1px solid #e6eddb;border-radius:8px;margin-top:10px;padding:13px 10px}.profile-item strong{justify-content:space-between;align-items:center;gap:7px;font-size:12px;font-weight:500;display:flex}.profile-item small,.profile-item>span{color:#a1b28a;margin-top:5px;font-size:10px;display:block}.form-two{grid-template-columns:1fr 1fr;gap:12px;display:grid}.admin-intro+.table-scroll+.microcopy{margin-top:15px}.login-page{grid-template-columns:1.1fr 1fr;min-height:100vh;display:grid}.login-illustration{background:#edf2e5;flex-direction:column;justify-content:space-between;padding:50px 9%;display:flex;position:relative;overflow:hidden}.login-illustration>div:nth-child(2){margin:60px 0 30px}.login-illustration h1{letter-spacing:1px;color:#385b36;margin:17px 0 20px;font-size:49px;font-weight:550;line-height:1.5}.login-illustration p{color:#92a77f;font-size:13px;line-height:2.1}.login-illustration .eyebrow{color:#8da478;letter-spacing:1px;font-size:11px}.decorative-ribbon{background:#dce9ca;border-top:1px solid #cfdfbd;border-bottom:1px solid #cfdfbd;justify-content:space-around;align-items:center;gap:20px;width:140%;margin-left:-20%;padding:28px 23px;display:flex;transform:rotate(-8deg);box-shadow:0 15px 30px #6e855518}.decorative-ribbon span{color:#9caf76;font-size:45px}.decorative-ribbon span:nth-child(3n+1){color:#d3aa7d;font-size:54px}.decorative-ribbon span:nth-child(3n+2){color:#cebf7c}.login-illustration>small{letter-spacing:3px;color:#a3b58f;margin-top:60px;font-size:9px}.login-form-wrap{background:#fff;justify-content:center;align-items:center;padding:40px;display:flex}.login-form{width:350px;max-width:100%}.login-form>h2{margin:9px 0 12px;font-size:27px}.login-form>.muted{margin-bottom:30px;font-size:12px}.login-form>label{color:#6e8563;margin-bottom:19px;font-size:12px;display:block}.login-form>label>input{margin-top:8px;padding:12px 14px}.login-form>.primary{justify-content:space-between;margin-top:10px}.login-demo{color:#a0af91;border-top:1px solid #e9efdf;margin-top:30px;padding-top:20px;font-size:11px}.login-demo strong{margin-bottom:8px;font-size:10px;font-weight:500;display:block}.login-demo span{margin:3px 0;font-size:10px;display:block}.login-demo small{color:#b0bda3;margin-top:12px;font-size:9px;display:block}@media (width>=1500px){.workspace-grid{grid-template-columns:315px minmax(480px,1fr) 310px;gap:24px}.source-section{padding:23px}.preview-stage{min-height:380px}.refinement-body textarea{min-height:185px}.template-card img{height:48px}.empty-canvas{min-height:280px}.panel-heading{padding-top:25px}.preview-stage.is-empty{min-height:380px}}@media (width<=1200px){.workspace-grid{grid-template-columns:260px minmax(300px,1fr) 255px;gap:14px}.app-shell main{padding:25px 2.5% 20px}.topbar{padding:0 2.5%}.source-section{padding:20px 17px}.panel-heading,.refinement-panel .panel-heading{padding-left:18px;padding-right:18px}.quota-card{margin-left:17px;margin-right:17px}.refinement-body{padding-left:17px;padding-right:17px}.preview-panel .panel-heading{padding:22px 17px 19px}.preview-stage{margin:0 17px}.result-actions{padding-left:17px;padding-right:17px}.panel-heading h2{max-width:190px;font-size:15px}.preview-stage{min-height:310px}.state-pill{font-size:8px}.stage-topline,.stage-bottomline{padding:11px}.refine-footer{padding:18px}.preview-caption{padding-left:17px;padding-right:17px}.history-panel{padding:18px 16px}.history-heading>span{font-size:8px}.template-card>span{font-size:10px}.selected-patterns{gap:7px}.pattern-tile .checker{height:59px;padding:7px}.template-card img{height:38px}.source-section .section-label>span{font-size:9px}.brand strong{font-size:18px}}@media (width<=1000px){.workspace-grid{grid-template-columns:250px minmax(360px,1fr);gap:18px}.refinement-panel{grid-area:2/2}.source-panel{grid-row:span 2}.center-column{grid-column:2}.refinement-panel .refinement-body{grid-template-columns:1fr 1fr;column-gap:15px;display:grid}.refinement-body>label,.refinement-body>p,.refinement-body textarea,.refinement-body>.text-limit{grid-column:1/-1}.refinement-body .suggestions{grid-column:1}.refinement-body>.refine-button{grid-area:5/2;align-self:center;height:45px}.refinement-body>.refine-help{grid-area:6/2}.refinement-body textarea{min-height:100px}.refinement-panel .panel-heading{padding-bottom:15px}.quota-card{padding:12px 17px}.quota-card>div:first-child>span{font-size:12px}.quota-dots{margin-top:8px}.refine-footer{padding:15px 20px}.refine-footer .test-limit{margin-top:7px}.environment-strip>div>span:last-child{display:none}.workspace-title h1{font-size:23px}.page-footer>span:nth-child(2){display:none}.login-illustration h1{font-size:38px}}@media (width<=700px){.topbar{height:70px;padding:0 18px}.brand strong{font-size:16px}.brand small{letter-spacing:1.5px;font-size:6px}.brand-icon svg{width:20px}.version-tag{display:none}.header-actions{gap:5px}.header-actions>.text-button{gap:0;padding:8px;font-size:0}.header-actions>.text-button .count,.header-divider,.user-name{display:none}.avatar{width:25px;height:25px;margin-left:5px}.app-shell main{padding:22px 16px 18px}.workspace-title{align-items:start;gap:10px}.workspace-title h1{margin:7px 0;font-size:21px;line-height:1.6}.workspace-title p{max-width:240px;font-size:10px;line-height:1.8}.workspace-title .eyebrow{font-size:8px}.workspace-title>.secondary{gap:0;margin-top:20px;padding:10px;font-size:0}.workspace-grid{grid-template-columns:1fr;gap:17px}.source-panel,.center-column,.refinement-panel{grid-area:auto/1}.source-panel{overflow:visible}.source-section{padding:18px}.source-panel .panel-heading{padding:20px 18px 0}.source-section:first-of-type .two-actions{max-width:300px}.selected-patterns{flex-wrap:wrap;gap:10px;display:flex}.pattern-tile{width:65px}.empty-patterns{padding:12px}.template-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:9px}.template-card img{height:34px}.template-card>span{font-size:10px}.template-card{padding:5px}.environment-strip{gap:7px;padding:9px 10px;font-size:9px}.environment-strip strong{font-size:9px}.outline-pill{padding:3px 5px;font-size:8px}.environment-strip>div{gap:6px}.background-section .two-actions,.background-selected{max-width:300px}.preview-stage{min-height:285px}.preview-stage.is-empty{min-height:300px}.preview-panel .panel-heading h2{max-width:225px}.history-panel{padding:20px 18px}.refinement-panel .refinement-body{display:block}.refinement-body textarea{min-height:130px}.suggestions{display:flex}.suggestions>button,.refine-footer p{font-size:10px}.page-footer{gap:12px;font-size:8px}.modal-scrim{padding:10px}.modal{border-radius:12px;max-height:94vh;padding:22px 18px}.modal-heading{margin-bottom:20px}.modal-heading h2{font-size:21px}.library-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.library-image{height:80px}.library-card strong{font-size:10px}.library-card>span{font-size:8px}.library-toolbar{gap:7px}.upload-label{padding:10px;font-size:10px}.library-toolbar input{min-width:0;font-size:11px}.modal-footer{gap:10px}.modal-footer>span{font-size:10px}.modal-footer>.primary{padding:10px 12px;font-size:11px}.admin-columns{grid-template-columns:1fr}.admin-existing{max-height:240px}.login-page{flex-direction:column;min-height:100vh;display:flex}.login-illustration{min-height:320px;padding:25px 30px 30px}.login-illustration>div:nth-child(2){margin:30px 0 0}.login-illustration h1{margin:10px 0 14px;font-size:30px;line-height:1.4}.login-illustration h1 br{display:none}.login-illustration p{font-size:11px}.decorative-ribbon,.login-illustration>small{display:none}.login-form-wrap{flex:1;padding:35px 30px 40px}.login-form>h2{font-size:24px}.login-form>.eyebrow{font-size:8px}.login-demo{margin-top:23px}.notice{font-size:11px}}@media (prefers-reduced-motion:reduce){*{transition:none!important;animation-duration:.01ms!important}}@container (width<=950px){.workspace-grid{grid-template-columns:250px minmax(0,1fr);gap:16px}.source-panel{grid-row:span 2}.center-column{grid-column:2}.refinement-panel{grid-area:2/2}.refinement-body textarea{min-height:120px}.topbar{flex-wrap:wrap;gap:12px}.workspace-title h1{font-size:22px}}@container (width<=700px){.workspace-grid{grid-template-columns:minmax(0,1fr)}.source-panel,.center-column,.refinement-panel{grid-area:auto/1}.topbar,.app-shell main{padding:14px}.workspace-title,.environment-strip{flex-wrap:wrap}.header-actions>.text-button{gap:5px;font-size:12px}.workspace-title>.secondary{margin-top:0;font-size:12px}}.template-option{flex-direction:column;gap:3px;min-width:0;display:flex}.template-option>.template-card{width:100%}.more-layouts{border-top:1px solid var(--line);margin-top:12px}.more-layouts-toggle{color:#345e45;background:0 0;border:0;justify-content:space-between;align-items:center;width:100%;min-height:40px;padding:9px 2px;font-size:13px;font-weight:600;display:flex}.more-layouts-toggle:hover{background:#edf3e9}.chosen-layout{justify-content:space-between;align-items:center;gap:8px;margin-top:8px;font-size:12px;display:flex}.chosen-layout .template-example-button{font-size:11px}.layout-picker-modal,.asset-library-modal,.design-library-modal{flex-direction:column;max-height:calc(100dvh - 48px);display:flex;overflow:hidden}.layout-picker-modal>.modal-heading,.asset-library-modal>.modal-heading,.design-library-modal>.modal-heading,.asset-library-modal>.library-toolbar,.asset-library-modal>.library-note,.asset-library-modal>.checkbox-line,.layout-picker-modal>.library-note,.layout-picker-modal>.modal-footer,.asset-library-modal>.modal-footer,.design-library-modal>.modal-footer{flex-shrink:0}.layout-picker-grid.template-grid{grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;min-height:0;padding:3px;overflow:auto}.asset-library-modal>.library-grid,.design-library-modal>.design-library{min-height:0;padding:3px;overflow:auto}.library-pagination{color:#526a5d;flex-shrink:0;justify-content:space-between;align-items:center;gap:12px;padding-top:16px;font-size:12px;display:flex}.design-loading{gap:12px}.preview-panel>.result-actions,.preview-panel>.generate-area{padding-top:0;padding-bottom:16px}.ai-draft-options{color:#3d5a43;background:#f7faf3;border:1px solid #e1e9da;border-radius:7px;margin-top:12px;padding:10px 12px;font-size:12px}.ai-draft-options>label{align-items:center;gap:8px;font-weight:600;display:flex}.ai-draft-options input{accent-color:#3b6c41;width:auto;margin:0}.ai-draft-options p{color:#65765f;margin:7px 0 0;font-size:11px;line-height:1.7}.ai-draft-reference{flex-wrap:wrap;align-items:center;gap:8px;margin-top:7px;font-size:11px;display:flex}.ai-draft-reference button,.ai-reference-picker{color:#345e45;text-underline-offset:3px;background:0 0;border:0;padding:4px 0;font-size:11px;text-decoration:underline}.ai-reference-picker{margin-top:5px}.layout-reference-help{color:#526a5d;margin-top:12px;font-size:13px;line-height:1.8}.choose-ai-reference{margin-top:14px;font-size:13px}.design-list-row{align-items:center;gap:10px;display:flex}.design-list-row>.design-list-item{flex:1;min-width:0}.design-list-item>div{min-width:0}.design-list-item strong{overflow-wrap:anywhere}.design-list-tabs{flex-shrink:0;gap:10px;padding-bottom:16px;display:flex}.design-list-tabs>button{border:1px solid var(--line);color:#526a5d;background:#fff;border-radius:6px;padding:8px 16px}.design-list-tabs>button.selected{color:#345e45;background:#edf3e9;border-color:#afc299}.delete-design-button{color:#965246;background:0 0;border:1px solid #eadbd7;border-radius:6px;flex-shrink:0;padding:9px 12px}.delete-design-confirm{color:#724638;background:#fff8f3;border:1px solid #e9d7cb;border-radius:8px;flex-shrink:0;margin-bottom:15px;padding:14px;font-size:13px}.delete-design-confirm>div{justify-content:flex-end;gap:10px;margin-top:12px;display:flex}.danger-button{color:#fff;background:#9e4634;border:1px solid #9e4634;border-radius:6px;padding:8px 14px;font-size:12px}@media (width<=700px){.layout-picker-grid.template-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.library-pagination{gap:6px;font-size:11px}.library-pagination .secondary{padding:8px}}.layout-selection-help,.layout-selection-issue{margin-top:12px;font-size:12px;line-height:1.7}.layout-selection-help{color:#526a5d}.layout-selection-issue{color:#9e4634}.template-rules-help{color:#526a5d;font-size:12px;line-height:1.7;display:block}.template-example-button,.template-examples-all{color:#345e45;text-underline-offset:3px;background:0 0;border:0;font-size:12px;font-weight:500;line-height:1.5;text-decoration:underline}.template-example-button{min-height:30px;padding:4px 6px}.template-examples-all{padding:4px 0 4px 8px}.template-example-button:hover,.template-examples-all:hover{color:#193f29;background:#edf3e9}.template-example-button:focus-visible,.template-examples-all:focus-visible{outline-offset:2px;outline:2px solid #507857}.layout-examples-modal{width:1160px}.pattern-role{color:#284a36;background:#fff;border:1px solid #b8c7b1;border-radius:5px;width:100%;min-width:0;min-height:30px;margin-top:5px;padding:3px 5px;font-size:12px}.selected-patterns.has-pattern-roles{grid-template-columns:repeat(2,minmax(80px,1fr))}.has-pattern-roles .pattern-tile{min-width:80px}.layout-examples-modal .modal-heading{z-index:2;background:#fff;margin-top:-12px;margin-bottom:14px;padding-top:12px;padding-bottom:12px;position:sticky;top:-27px}.layout-examples-intro{margin-bottom:22px}.layout-mode-summary{color:#284a36;margin:0 0 8px;font-size:16px;line-height:1.65}.layout-mode-note{color:#455b49;background:#f2f6ee;border-left:3px solid #90a77f;margin:8px 0 12px;padding:10px 13px;font-size:14px;line-height:1.7}.layout-examples-tools{flex-wrap:wrap;align-items:center;gap:14px;display:flex}.layout-examples-tools>button{min-height:34px;font-size:13px}.case-mode-filter{align-items:center;gap:8px;font-size:14px;display:flex}.case-mode-filter select{min-height:36px}.layout-case-navigation{align-items:center;gap:12px;margin:14px 0;display:flex}.layout-case-navigation>label{flex:1;align-items:center;gap:12px;min-width:0;display:flex}.layout-case-navigation>label>span{white-space:nowrap;color:#42583d;font-size:13px}.layout-case-navigation select{flex:1;min-width:0;min-height:36px}.layout-example-kind{flex-wrap:wrap;gap:8px;margin:12px 0 18px;display:flex}.layout-example-kind button{color:#37513d;background:#fff;border:1px solid #bdcdb6;border-radius:6px;padding:8px 14px;font-size:14px}.layout-example-kind button.selected{background:#e9f0e4;border-color:#67855b;font-weight:600}.layout-example-difference{color:#695626;margin:8px 0 0;font-size:14px;line-height:1.7}.layout-demo-note{color:#42583d;font-size:14px;line-height:1.7}.layout-demos figure{border-top:1px solid #dbe5d7;margin:16px 0;padding-top:14px}.layout-demos figcaption{flex-direction:column;gap:6px;margin-bottom:8px;font-size:14px;line-height:1.6;display:flex}.layout-demos figcaption span{color:#42583d}.layout-demos figure>img{object-fit:contain;background:#f6f8f2;border:1px solid #dbe5d7;border-radius:5px;width:100%;height:auto;max-height:250px;display:block}@media (width<=600px){.layout-case-navigation{gap:6px}.layout-case-navigation>label{flex-direction:column;align-items:stretch;gap:4px}}.layout-examples-loading,.layout-examples-error{color:#37513d;flex-wrap:wrap;align-items:center;gap:14px;min-height:140px;display:flex}.layout-examples-error{padding:20px 0;display:block}.layout-examples-error>p{margin:0 0 16px;font-size:15px;line-height:1.7}.layout-examples-list{flex-direction:column;gap:22px;display:flex}.layout-example{border-top:1px solid #dbe5d7;min-width:0;padding-top:18px}.layout-example-heading{flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:12px;display:flex}.layout-example-heading h3{color:#284a36;margin:0;font-size:19px;line-height:1.5}.layout-example-heading>div{flex-wrap:wrap;align-items:center;gap:12px;display:flex}.layout-example-code{color:#50624d;font-variant-numeric:tabular-nums;font-size:13px}.layout-reference-tag{color:#6b5828;background:#f4f1e6;border-radius:4px;padding:3px 7px;font-size:12px}.layout-example-description{color:#304f3a;margin:8px 0 0;font-size:15px;line-height:1.7}.layout-example-image-tools{align-items:center;gap:12px;min-height:38px;display:flex}.layout-example-image-tools>button{color:#335c40;min-height:34px;padding:5px 0;font-size:13px}.layout-example-image-tools>span{color:#53644d;font-size:12px}.layout-example-viewport{background:#f7f9f5;border:1px solid #e3e9df;border-radius:5px;overflow:auto hidden}.layout-example-viewport>img{width:100%;max-width:none;height:auto;display:block}.layout-example-viewport.is-zoomed>img{width:max(100%, var(--example-width))}.layout-example-viewport:focus-visible{outline-offset:3px;outline:2px solid #507857}.layout-example-look{color:#3e5941;margin:10px 0 0;font-size:14px;line-height:1.7}.layout-example-look strong{font-weight:600}.layout-example-reference{color:#6b5828;margin:8px 0 0;font-size:13px;line-height:1.7}.layout-example-unavailable{color:#465d48;background:#f7f9f5;border:1px dashed #b8c7b1;border-radius:5px;margin-top:14px;padding:18px;font-size:14px;line-height:1.7}.layout-example-unavailable p{margin:0}.layout-example-unavailable button{margin-top:12px;font-size:13px}.layout-examples-source{color:#53644d;border-top:1px solid #dbe5d7;margin:20px 0 0;padding-top:14px;font-size:12px;line-height:1.8}.background-prompt-label{color:var(--ink);margin:12px 0 6px;font-size:13px;font-weight:600;display:block}.background-prompt{box-sizing:border-box;border:1px solid var(--line);width:100%;min-height:66px;color:var(--ink);font:inherit;resize:vertical;background:#fff;border-radius:6px;padding:9px 10px;font-size:13px;line-height:1.65;display:block}.background-prompt:focus{outline-offset:2px;outline:2px solid #91a88a}.model-help,.model-edit-boundary{color:#4c634f;font-size:13px;line-height:1.7}.refinement-body .model-edit-boundary{border-left:2px solid #b4c6ab;margin:0 0 12px;padding-left:9px}.model-workflow-help{color:#4c634f;margin-bottom:16px;font-size:13px;line-height:1.7}.model-workflow-help summary{cursor:pointer;font-weight:600}.model-workflow-help p{margin:8px 0 0}@media (width<=600px){.layout-examples-modal .modal-heading{top:-20px}.layout-examples-modal .modal-heading h2{font-size:20px}.layout-mode-summary{font-size:15px}.layout-example-heading h3{font-size:17px}.layout-example-heading{gap:4px}}.background-tone-control{color:#42584b;align-items:center;gap:8px;margin-top:12px;font-size:13px;display:flex}.background-tone-control input[type=checkbox]{accent-color:#386b43;width:16px;height:16px;margin:0}.density-control{align-items:center;gap:12px;margin-top:12px;font-size:13px;display:flex}.density-control select{color:#203c2a;background:#fff;border:1px solid #d7dfd6;border-radius:6px;flex:1;min-width:0;padding:6px 10px}.loop-preview{min-width:0;padding:0 15px 12px}.loop-view-heading{color:#35523d;flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:8px;margin:0 0 10px;display:flex}.loop-view-heading strong{font-size:13px;font-weight:600}.loop-view-heading>span{font-variant-numeric:tabular-nums;font-size:10px}.loop-unit-view{justify-content:center;align-items:center;min-height:150px;padding:14px 0;display:flex}.loop-unit-view .target-layer>img{width:auto;max-width:100%;height:auto;max-height:220px;display:block;box-shadow:0 5px 14px #33513514}.loop-continuity{min-width:0;padding:14px 0}.loop-unit-view[hidden],.loop-continuity[hidden]{display:none}.loop-continuity-track{grid-template-columns:repeat(3,minmax(0,1fr));align-items:stretch;display:grid}.loop-repeat{min-width:0;position:relative}.loop-repeat>img{border:0;border-radius:0;width:100%;max-width:none;height:auto;display:block}.loop-continuity-track.show-seams>.loop-repeat+.loop-repeat:before{content:\"\";z-index:1;pointer-events:none;border-left:2px dashed #aa3d4c;width:0;position:absolute;top:-9px;bottom:-9px;left:-1px}.loop-preview-tools{flex-wrap:wrap;align-items:center;gap:14px;padding-top:8px;display:flex}.loop-view-button{color:#305e3d;background:#fff;border:1px solid #bacbb1;border-radius:6px;min-height:32px;padding:6px 10px;font-size:12px}.loop-view-button[aria-pressed=true]{background:#e8f0e2}.loop-seam-toggle{color:#486044;align-items:center;gap:6px;font-size:12px;display:inline-flex}.loop-seam-toggle input{accent-color:#386b43;width:15px;height:15px;margin:0}.loop-preview-note{color:#53664d;margin:9px 0 0;font-size:11px;line-height:1.7}.loop-check{color:#3e5d38;background:#edf4e8;border:1px solid #d5e1ce;border-radius:6px;margin-top:10px;padding:9px 11px;font-size:11px;line-height:1.7}.loop-check>strong{margin-right:9px;font-weight:600;display:inline}.loop-check.needs-review{color:#73552a;background:#fff8e9;border-color:#e7d7b4}.loop-check ul{margin:6px 0 0;padding-left:17px}.loop-check li.error{color:#933f35}.loop-mode-notice{color:#725832;margin-top:8px;font-size:11px;line-height:1.7}.loop-technical-details{color:#53664d;margin-top:9px;font-size:11px;line-height:1.7}.loop-technical-details summary{cursor:pointer;width:fit-content}.loop-technical-details dl{margin:7px 0 0}.loop-technical-details dl>div{gap:12px;display:flex}.loop-technical-details dt{flex:none}.loop-technical-details dd{overflow-wrap:anywhere;margin:0}@media (width<=600px){.loop-preview{padding-left:10px;padding-right:10px}.loop-unit-view{min-height:110px}.loop-unit-view .target-layer>img{max-height:170px}.loop-view-heading{display:block}.loop-view-heading>span{margin-top:3px;display:block}}.target-layer{max-width:100%;position:relative}.target-overlay{pointer-events:none;width:100%;height:100%;position:absolute;inset:0;overflow:hidden}.target-overlay rect{fill:#3c81661f;stroke:#16674d;stroke-width:2px}.optional-layers,.target-picker{padding:12px 0}.optional-layers summary{cursor:pointer;font-weight:600}.optional-layers>div,.target-picker{flex-wrap:wrap;align-items:center;gap:8px;display:flex}.optional-layers>div{margin-top:8px}.target-picker select{flex:1;min-width:0;max-width:100%}.compact-status.environment-strip{color:#485c4d;flex-wrap:wrap;justify-content:flex-start;min-height:0;margin:8px 0;padding:7px 12px}.compact-status.environment-strip span{font-size:12px;display:inline}.workspace-grid{margin-top:12px}.remaining-edits{color:#375646;margin:0 20px 4px;font-size:14px}.refinement-body .target-picker{padding:8px 0}.panel-heading h2{margin:0}.refine-footer p{color:#42584b}@media (width>=850px){.workspace-grid.draft-workspace{grid-template-columns:minmax(232px,300px) minmax(0,1fr)}}.history-panel summary{cursor:pointer;color:#344b3e;font-size:14px;font-weight:600}.suggestions{margin-top:12px}.image-recovery{color:#73552a;background:#fff8e9;flex-direction:column;justify-content:center;align-items:center;gap:8px;min-height:90px;padding:10px;font-size:13px;line-height:1.6;display:flex}.image-recovery [role=button]{cursor:pointer;align-items:center;min-height:32px;display:flex}.image-loading{color:#42584b;padding:3px;font-size:12px;line-height:1.6;display:block}.target-layer .image-loading,.loop-repeat .image-loading{position:absolute;bottom:0;left:0;right:0}.preview-stage{min-height:230px}@media (width>=1100px){.preview-column{align-self:start;position:sticky;top:12px}.refinement-panel{align-self:start}}.workspace-grid{grid-template-columns:220px minmax(0,1fr) 250px;gap:16px}@media (width>=1500px){.workspace-grid{grid-template-columns:230px minmax(0,1fr) 260px;gap:20px}}@container (width>=701px) and (width<=1050px){.workspace-grid{grid-template-rows:max-content max-content minmax(0,1fr);grid-template-columns:220px minmax(0,1fr)}.source-panel{grid-row:1/span 3}.center-column{grid-area:1/2}.refinement-panel{grid-area:2/2}}@container (width>=1051px){.center-column{align-self:start;position:sticky;top:12px}}@container (width<=700px){.workspace-grid,.workspace-grid.draft-workspace{grid-template-columns:minmax(0,1fr)}.source-panel,.center-column,.refinement-panel{grid-area:auto/1}}.library-note,.hide-asset,.library-card>span,.modal-footer>span{color:#42584b}.loop-resolution-note{color:#7a5a12;background:#fffaf0;border:1px solid #f0dfb4;border-radius:8px;margin:6px 0 0;padding:8px 12px;font-size:12.5px;line-height:1.6}";
// src/embed.tsx
function N(e, t) {
	let n = e.shadowRoot || e.attachShadow({ mode: "open" }), r = document.createElement("style");
	r.textContent = M;
	let i = document.createElement("div");
	n.replaceChildren(r, i), v(t);
	let a = (0, u.createRoot)(i), o = !0, s = "ribbon", c = () => a.render(/* @__PURE__ */ (0, C.jsx)(we, {
		active: o,
		view: s
	}));
	return c(), {
		setView(e, t = !0) {
			o = t, s = e, c();
		},
		unmount() {
			a.unmount(), n.replaceChildren();
		}
	};
}
export { N as mount };
