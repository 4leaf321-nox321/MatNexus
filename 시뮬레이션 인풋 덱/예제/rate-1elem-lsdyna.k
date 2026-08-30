$-------------------------------------------------------------------------------
$ Rate-dependent plasticity, single element  --  LS-DYNA
$
$   units : ton - mm - s   (force N, stress MPa)
$   model : same 1 mm cube and 1/8 symmetry as the DP600 quasi-static deck,
$           pulled on an EXPONENTIAL history so the TRUE strain rate is exactly
$           100 /s :  u(t) = exp(100 t) - 1 ,  t = 0 .. 0.00405465 s
$   check : sig_x ~= 770.30 MPa , reaction ~= 514.29 N
$           (quasi-static 700.32 MPa x the 1.10 rate factor)
$
$   *MAT_024 fields C and P are Cowper-Symonds:
$       sigma = sigma_static * [1 + (eps_dot/C)^(1/P)]
$   C = 1.0e7 /s and P = 5 give a factor of 1.10 at 100 /s.
$   The classic "mild steel" pair C = 40, P = 5 would give 2.66 at this rate --
$   it is a fit for much lower rates and badly overpredicts if reused blindly.
$
$   VP = 1 uses the PLASTIC strain rate.  With VP = 0 the total strain rate is
$   used, which carries the elastic wave ringing straight into the yield stress.
$
$   SIGY/ETAN stay 0 because LCSS points at the quasi-static curve; when LCSS
$   is set, SIGY and ETAN are ignored.
$-------------------------------------------------------------------------------
*KEYWORD
*TITLE
Rate-dependent plasticity 1-element, 100/s (ton-mm-s)
$
$===============================================================================
$ CONTROL / OUTPUT
$===============================================================================
*CONTROL_TERMINATION
$#  endtim    endcyc     dtmin    endeng    endmas     nosol
0.00405465         0       0.0       0.0       0.0         0
*CONTROL_ENERGY
$#    hgen      rwen    slnten     rylen
         2         2         2         2
*DATABASE_GLSTAT
$#      dt    binary      lcur     ioopt
   1.0E-05         0         0         1
*DATABASE_ELOUT
   1.0E-05         0         0         1
*DATABASE_NODFOR
   1.0E-05         0         0         1
*DATABASE_BINARY_D3PLOT
$#      dt      lcdt      beam     npltc    psetid
   2.0E-04
*DATABASE_HISTORY_SOLID
$#    id1
         1
*DATABASE_NODAL_FORCE_GROUP
$#    nsid       cid
         4
$
$===============================================================================
$ PART / SECTION / MATERIAL
$===============================================================================
*PART
one hex
$#     pid     secid       mid     eosid      hgid      grav    adpopt      tmid
         1         1         1         0         0         0         0         0
*SECTION_SOLID_TITLE
constant stress hex (ELFORM=1)
$#   secid    elform       aet
         1         1         0
*MAT_PIECEWISE_LINEAR_PLASTICITY_TITLE
DP600 with Cowper-Symonds rate   C=1.0e7  P=5
$#     mid        ro         e        pr      sigy      etan      fail      tdel
         1 7.850E-09 2.100E+05     0.300     0.000     0.000     0.000     0.000
$#       c         p      lcss      lcsr        vp
 1.000E+07     5.000       100         0         1
$#    eps1      eps2      eps3      eps4      eps5      eps6      eps7      eps8
     0.000     0.000     0.000     0.000     0.000     0.000     0.000     0.000
$#     es1       es2       es3       es4       es5       es6       es7       es8
     0.000     0.000     0.000     0.000     0.000     0.000     0.000     0.000
$
$ quasi-static curve: true stress vs EFFECTIVE PLASTIC strain
*DEFINE_CURVE_TITLE
DP600 quasi-static hardening
$#    lcid      sidr       sfa       sfo      offa      offo    dattyp
       100         0     1.000     1.000     0.000     0.000         0
$#                a1                  o1
              0.0000            350.0000
              0.0200            455.0000
              0.1000            560.0000
              0.4000            700.0000
              1.0000            790.0000
$
$===============================================================================
$ MESH
$===============================================================================
*NODE
$#   nid               x               y               z      tc      rc
       1             0.0             0.0             0.0       0       0
       2             1.0             0.0             0.0       0       0
       3             1.0             1.0             0.0       0       0
       4             0.0             1.0             0.0       0       0
       5             0.0             0.0             1.0       0       0
       6             1.0             0.0             1.0       0       0
       7             1.0             1.0             1.0       0       0
       8             0.0             1.0             1.0       0       0
*ELEMENT_SOLID
$#   eid     pid      n1      n2      n3      n4      n5      n6      n7      n8
       1       1       1       2       3       4       5       6       7       8
$
$===============================================================================
$ NODE SETS
$===============================================================================
*SET_NODE_LIST_TITLE
x = 0 face
$#     sid       da1       da2       da3       da4
         1       0.0       0.0       0.0       0.0
$#    nid1      nid2      nid3      nid4
         1         4         5         8
*SET_NODE_LIST_TITLE
y = 0 face
         2       0.0       0.0       0.0       0.0
         1         2         5         6
*SET_NODE_LIST_TITLE
z = 0 face
         3       0.0       0.0       0.0       0.0
         1         2         3         4
*SET_NODE_LIST_TITLE
x = 1 face (pulled)
         4       0.0       0.0       0.0       0.0
         2         3         6         7
$
$===============================================================================
$ BOUNDARY CONDITIONS
$===============================================================================
*BOUNDARY_SPC_SET
$#    nsid       cid      dofx      dofy      dofz     dofrx     dofry     dofrz
         1         0         1         0         0         0         0         0
         2         0         0         1         0         0         0         0
         3         0         0         0         1         0         0         0
$
*BOUNDARY_PRESCRIBED_MOTION_SET
$#    nsid       dof       vad      lcid        sf       vid     death     birth
         4         1         2       200     1.000         0 1.000E+28     0.000
$
$ u(t) = exp(100 t) - 1  ->  true strain rate is exactly 100 /s
*DEFINE_CURVE_TITLE
exponential pull, constant true strain rate 100/s
$#    lcid      sidr       sfa       sfo      offa      offo    dattyp
       200         0     1.000     1.000     0.000     0.000         0
$#                a1                  o1
           0.0000000            0.000000
           0.0002027            0.020480
           0.0004055            0.041380
           0.0006082            0.062707
           0.0008109            0.084472
           0.0010137            0.106682
           0.0012164            0.129347
           0.0014191            0.152476
           0.0016219            0.176079
           0.0018246            0.200165
           0.0020273            0.224745
           0.0022301            0.249828
           0.0024328            0.275425
           0.0026355            0.301545
           0.0028383            0.328201
           0.0030410            0.355403
           0.0032437            0.383162
           0.0034465            0.411489
           0.0036492            0.440397
           0.0038519            0.469896
           0.0040547            0.500000
$
*END
