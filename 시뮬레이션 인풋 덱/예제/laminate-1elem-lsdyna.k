$-------------------------------------------------------------------------------
$ Quasi-isotropic laminate, single shell element  --  LS-DYNA
$
$   units : ton - mm - s   (force N, stress MPa, density 1.57e-9)
$   model : 1 x 1 mm shell, 4 plies [0/45/-45/90] x 0.125 mm = 0.5 mm
$           membrane only (all rotations and uz fixed), pulled to ux = 0.005 mm
$   check : laminate average sig_x ~= 260.45 MPa, edge reaction ~= 130.23 N
$           (CLT: E_eff = 52090.3 MPa)
$
$   PRBA IS THE MINOR POISSON RATIO.  MAT_054 asks for nu_ba, and the symmetry
$   nu_ba/E_b = nu_ab/E_a gives nu_ba = 0.3 * 9000/135000 = 0.02.  Entering the
$   major 0.3 here would imply nu_ab = 4.5 and LS-DYNA rejects the material --
$   which is the good case; the bad case is a deck that runs with the wrong one.
$
$   *PART_COMPOSITE replaces *SECTION_SHELL + *INTEGRATION_SHELL: the ply
$   material, thickness and angle are listed directly, two plies per card.
$-------------------------------------------------------------------------------
*KEYWORD
*TITLE
QI laminate 1-element tension (ton-mm-s)
$
$===============================================================================
$ CONTROL / OUTPUT
$===============================================================================
*CONTROL_TERMINATION
$#  endtim    endcyc     dtmin    endeng    endmas     nosol
     0.001         0       0.0       0.0       0.0         0
*CONTROL_ENERGY
$#    hgen      rwen    slnten     rylen
         2         2         2         2
*CONTROL_SHELL
$#  wrpang     esort     irnxx    istupd    theory       bwc     miter      proj
      20.0         0        -1         0         2         2         1         0
*DATABASE_GLSTAT
$#      dt    binary      lcur     ioopt
   1.0E-06         0         0         1
*DATABASE_ELOUT
   1.0E-06         0         0         1
*DATABASE_NODFOR
   1.0E-06         0         0         1
*DATABASE_BINARY_D3PLOT
$#      dt      lcdt      beam     npltc    psetid
   5.0E-05
*DATABASE_EXTENT_BINARY
$#   neiph     neips    maxint    strflg    sigflg    epsflg    rltflg    engflg
         0         0         4         1         1         1         1         1
*DATABASE_HISTORY_SHELL
$#    id1
         1
*DATABASE_NODAL_FORCE_GROUP
$#    nsid       cid
         4
$
$===============================================================================
$ PART_COMPOSITE  (layup)
$===============================================================================
*PART_COMPOSITE
QI laminate [0/45/-45/90]
$#     pid    elform      shrf      nloc     marea      hgid    adpopt    thshel
         1        16     0.833       0.0       0.0         0         0         0
$#    mid1    thick1        b1     tmid1      mid2    thick2        b2     tmid2
         1     0.125       0.0         0         1     0.125      45.0         0
         1     0.125     -45.0         0         1     0.125      90.0         0
$
$===============================================================================
$ PLY MATERIAL
$   Card 1  MID RO EA EB EC PRBA PRCA PRCB
$   Card 2  GAB GBC GCA (KF) AOPT
$   Card 3  XP YP ZP A1 A2 A3 MANGLE
$   Card 4  V1 V2 V3 D1 D2 D3 DFAILM DFAILS
$   Card 5  TFAIL ALPH SOFT FBRT YCFAC DFAILT DFAILC EFS
$   Card 6  XC XT YC YT SC CRIT BETA
$===============================================================================
*MAT_ENHANCED_COMPOSITE_DAMAGE_TITLE
CFRP UD ply   E1=135 GPa  E2=9 GPa   CRIT=54 (Chang-Chang)
$#     mid        ro        ea        eb        ec      prba      prca      prcb
         1 1.570E-09 135000.00   9000.00   9000.00      0.02      0.02      0.40
$#     gab       gbc       gca        kf      aopt
   5000.00   3500.00   5000.00       0.0       0.0
$#      xp        yp        zp        a1        a2        a3    mangle
       0.0       0.0       0.0       0.0       0.0       0.0       0.0
$#      v1        v2        v3        d1        d2        d3    dfailm    dfails
       0.0       0.0       0.0       0.0       0.0       0.0       0.0       0.0
$#   tfail      alph      soft      fbrt     ycfac    dfailt    dfailc       efs
       0.0       0.0       1.0       0.0       2.0       0.0       0.0       0.0
$#      xc        xt        yc        yt        sc      crit      beta
   1400.00   2200.00    200.00     60.00     90.00     54.00       0.0
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
*ELEMENT_SHELL
$#   eid     pid      n1      n2      n3      n4
       1       1       1       2       3       4
$
$===============================================================================
$ NODE SETS
$===============================================================================
*SET_NODE_LIST_TITLE
x = 0 edge
$#     sid       da1       da2       da3       da4
         1       0.0       0.0       0.0       0.0
$#    nid1      nid2
         1         4
*SET_NODE_LIST_TITLE
y = 0 edge
         2       0.0       0.0       0.0       0.0
         1         2
*SET_NODE_LIST_TITLE
all nodes
         3       0.0       0.0       0.0       0.0
         1         2         3         4
*SET_NODE_LIST_TITLE
x = 1 edge (pulled)
         4       0.0       0.0       0.0       0.0
         2         3
$
$===============================================================================
$ BOUNDARY CONDITIONS   (membrane only + pulled edge)
$===============================================================================
*BOUNDARY_SPC_SET
$#    nsid       cid      dofx      dofy      dofz     dofrx     dofry     dofrz
         1         0         1         0         0         0         0         0
         2         0         0         1         0         0         0         0
         3         0         0         0         1         1         1         1
$
$ VAD = 2 -> prescribed DISPLACEMENT, dof = 1 -> x
*BOUNDARY_PRESCRIBED_MOTION_SET
$#    nsid       dof       vad      lcid        sf       vid     death     birth
         4         1         2       200     1.000         0 1.000E+28     0.000
*DEFINE_CURVE_TITLE
pull ramp:  0 -> 0.005 mm over 0.001 s
$#    lcid      sidr       sfa       sfo      offa      offo    dattyp
       200         0     1.000     1.000     0.000     0.000         0
$#                a1                  o1
              0.0000              0.0000
              0.0010              0.0050
$
*END
